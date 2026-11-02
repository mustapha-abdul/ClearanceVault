import secrets
import hmac
import logging
import uuid
from pathlib import Path

import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.http import require_POST

from .models import (
    Document,
    ClearanceItem,
    UserSubscription,
    SharedDocument,
    PaymentTransaction,
)

logger = logging.getLogger(__name__)


# =====================================================
# COMMON PAGE RENDERER
# =====================================================

def show_page(request, page, **context):
    context["page"] = page
    return render(request, "index.html", context)
# =====================================================
# MATHEMATICAL CAPTCHA
# =====================================================

def generate_math_captcha(request):

    first_number = secrets.randbelow(9) + 1
    second_number = secrets.randbelow(9) + 1

    correct_answer = first_number + second_number

    request.session["registration_math_answer"] = str(correct_answer)

    return f"{first_number} + {second_number} = ?"

# =====================================================
# SUBSCRIPTION AND STORAGE HELPERS
# =====================================================

def get_user_subscription(user):
    subscription, created = UserSubscription.objects.get_or_create(
        user=user,
        defaults={
            "plan": "free",
            "status": "active",
        }
    )
    return subscription


def get_storage_used(user):
    documents = Document.objects.filter(owner=user)

    total = 0

    for document in documents:
        try:
            if document.file:
                total += document.file.size
        except (OSError, ValueError):
            continue

    return total


# =====================================================
# ADMIN PERMISSION CHECK
# IMPORTANT: THIS MUST COME BEFORE ADMIN DECORATORS
# =====================================================

def is_clearancevault_admin(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
    )


# =====================================================
# CUSTOM ADMIN DASHBOARD
# =====================================================

@user_passes_test(
    is_clearancevault_admin,
    login_url="login"
)
def admin_dashboard(request):

    search_query = request.GET.get("q", "").strip()

    users = User.objects.all().order_by("-date_joined")

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )

    context = {
        "users": users[:100],
        "search_query": search_query,

        "total_users": User.objects.count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "inactive_users": User.objects.filter(is_active=False).count(),
        "staff_users": User.objects.filter(is_staff=True).count(),

        "total_documents": Document.objects.count(),
        "total_subscriptions": UserSubscription.objects.count(),
        "paid_subscriptions": UserSubscription.objects.filter(
            plan__in=["plus", "pro"],
            status="active"
        ).count(),

        "total_payments": PaymentTransaction.objects.count(),
        "successful_payments": PaymentTransaction.objects.filter(
            status="success"
        ).count(),
        "pending_payments": PaymentTransaction.objects.filter(
            status="pending"
        ).count(),
    }

    return render(request, "admin.html", context)


# =====================================================
# ADMIN: VIEW USER DETAILS
# =====================================================

@user_passes_test(is_clearancevault_admin, login_url="login")
def admin_user_detail(request, user_id):

    account = get_object_or_404(User, pk=user_id)

    subscription = get_user_subscription(account)

    documents = Document.objects.filter(
        owner=account
    ).order_by("-uploaded_at")

    payments = PaymentTransaction.objects.filter(
        user=account
    ).order_by("-created_at")

    return render(request, "admin_user_detail.html", {
        "account": account,
        "subscription": subscription,
        "documents": documents,
        "payments": payments,
        "total_documents": documents.count(),
        "total_payments": payments.count(),
        "successful_payments": payments.filter(
            status="success"
        ).count(),
    })


# =====================================================
# ADMIN: ACTIVATE / DEACTIVATE USER
# =====================================================

@user_passes_test(is_clearancevault_admin, login_url="login")
@require_POST
def admin_toggle_user_status(request, user_id):

    account = get_object_or_404(User, pk=user_id)

    if account.pk == request.user.pk:
        messages.error(
            request,
            "You cannot change your own administrator account status."
        )
        return redirect("admin_user_detail", user_id=user_id)

    if account.is_superuser or account.is_staff:
        messages.error(
            request,
            "Administrator accounts cannot be changed here."
        )
        return redirect("admin_user_detail", user_id=user_id)

    account.is_active = not account.is_active
    account.save(update_fields=["is_active"])

    status_text = "activated" if account.is_active else "deactivated"

    messages.success(
        request,
        f"{account.username}'s account has been {status_text}."
    )

    return redirect("admin_user_detail", user_id=user_id)


# =====================================================
# ADMIN: CHANGE SUBSCRIPTION PLAN
# =====================================================

@user_passes_test(is_clearancevault_admin, login_url="login")
@require_POST
def admin_change_user_plan(request, user_id):

    account = get_object_or_404(User, pk=user_id)

    if account.is_superuser or account.is_staff:
        messages.error(
            request,
            "Administrator subscriptions cannot be changed here."
        )
        return redirect("admin_user_detail", user_id=user_id)

    selected_plan = request.POST.get("plan", "").strip().lower()

    valid_plans = dict(UserSubscription.PLAN_CHOICES)

    if selected_plan not in valid_plans:
        messages.error(
            request,
            "Please select a valid subscription plan."
        )
        return redirect("admin_user_detail", user_id=user_id)

    subscription = get_user_subscription(account)
    subscription.plan = selected_plan

    subscription.save(update_fields=["plan", "updated_at"])

    messages.success(
        request,
        f"{account.username}'s plan is now "
        f"{valid_plans[selected_plan]}."
    )

    messages.warning(
        request,
        "This is a manual plan change. It does not charge the customer "
        "or modify their Paystack billing agreement."
    )

    return redirect("admin_user_detail", user_id=user_id)


# =====================================================
# ADMIN: DELETE USER ACCOUNT
# =====================================================

def delete_user_document_files(files_to_delete):

    for storage, file_name in files_to_delete:
        try:
            storage.delete(file_name)
        except Exception:
            logger.exception(
                "Could not delete uploaded file: %s",
                file_name
            )


@user_passes_test(is_clearancevault_admin, login_url="login")
@require_POST
def admin_delete_user(request, user_id):

    account = get_object_or_404(User, pk=user_id)

    if account.pk == request.user.pk:
        messages.error(
            request,
            "You cannot delete your own administrator account."
        )
        return redirect("admin_dashboard")

    if account.is_superuser or account.is_staff:
        messages.error(
            request,
            "Administrator accounts cannot be deleted here."
        )
        return redirect("admin_dashboard")

    username = account.username

    files_to_delete = [
        (document.file.storage, document.file.name)
        for document in Document.objects.filter(owner=account)
        if document.file
    ]

    with transaction.atomic():
        account.delete()

        transaction.on_commit(
            lambda: delete_user_document_files(files_to_delete)
        )

    messages.success(
        request,
        f"The account {username} and its associated records have been deleted."
    )

    return redirect("admin_dashboard")


# =====================================================
# HOME
# =====================================================

def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    return show_page(request, "home")


# =====================================================
# EMAIL HELPER
# =====================================================

def send_account_email(subject, message, email):
    return send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False
    )


# =====================================================
# SEND VERIFICATION EMAIL
# =====================================================

def send_verification_email(request, user):

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    verification_url = request.build_absolute_uri(
        reverse(
            "verify_email",
            kwargs={
                "uidb64": uid,
                "token": token
            }
        )
    )

    subject = "Verify your ClearanceVault account"

    message = f"""
Hello {user.first_name},

Welcome to ClearanceVault!

Please verify your email address by clicking this link:

{verification_url}

Your verification link expires after 24 hours.

If you did not create this account, ignore this email.

ClearanceVault Team
"""

    return send_account_email(subject, message, user.email)


# =====================================================
# REGISTRATION WITH MATH CAPTCHA
# =====================================================

def register(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")
        math_answer = request.POST.get("math_answer", "").strip()

        # Retrieve the correct answer from the session.
        correct_answer = request.session.pop(
            "registration_math_answer",
            None
        )

        # Validate CAPTCHA first.
        if (
            not correct_answer
            or not math_answer
            or not hmac.compare_digest(
                math_answer,
                correct_answer
            )
        ):

            messages.error(
                request,
                "Incorrect maths answer. Please solve the new question."
            )

        elif not name or not email or not password or not confirm_password:

            messages.error(
                request,
                "Please complete all fields."
            )

        elif User.objects.filter(email__iexact=email).exists():

            messages.error(
                request,
                "This email address is already registered."
            )

        elif password != confirm_password:

            messages.error(
                request,
                "Passwords do not match."
            )

        else:

            name_parts = name.split()

            try:

                validate_password(password)

                with transaction.atomic():

                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=password,
                        first_name=name_parts[0],
                        last_name=" ".join(name_parts[1:]),
                        is_active=False
                    )

                    UserSubscription.objects.create(
                        user=user,
                        plan="free",
                        status="active"
                    )

                try:

                    send_verification_email(request, user)

                except Exception:

                    logger.exception(
                        "Registration verification email failed."
                    )

                    messages.warning(
                        request,
                        "Your account was created, but we could not send "
                        "the verification email. Please try resending it."
                    )

                    return redirect("resend_verification")

                messages.success(
                    request,
                    "Your account has been created! "
                    "Check your email and click the verification link "
                    "before logging in."
                )

                return redirect("login")

            except ValidationError as error:

                for error_message in error.messages:
                    messages.error(request, error_message)

            except Exception:

                logger.exception("Registration failed.")

                messages.error(
                    request,
                    "We could not create your account. Please try again."
                )

    # Generate a fresh question for the page.
    math_question = generate_math_captcha(request)

    return show_page(
        request,
        "register",
        math_question=math_question
    )


# =====================================================
# LOGIN
# =====================================================

def login_page(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        account = User.objects.filter(
            email__iexact=email
        ).first()

        if account and not account.is_active:

            if account.check_password(password):

                messages.warning(
                    request,
                    "Your email has not been verified. "
                    "Please verify your email before logging in."
                )

            else:

                messages.error(
                    request,
                    "Invalid email address or password."
                )

        else:

            user = None

            if account:
                user = authenticate(
                    request,
                    username=account.username,
                    password=password
                )

            if user is not None:

                login(request, user)

                # Send administrators to the admin dashboard.
                if user.is_staff and user.is_superuser:
                    return redirect("admin_dashboard")

                # Send normal users to their dashboard.
                return redirect("dashboard")


            messages.error(
                request,
                "Invalid email address or password."
            )

    return show_page(request, "login")


# =====================================================
# VERIFY EMAIL
# =====================================================

def verify_email(request, uidb64, token):

    try:

        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)

    except (
        TypeError,
        ValueError,
        OverflowError,
        User.DoesNotExist
    ):

        user = None

    if user is None:

        messages.error(
            request,
            "This verification link is invalid."
        )

        return redirect("login")

    if user.is_active:

        get_user_subscription(user)

        messages.info(
            request,
            "Your email has already been verified. You can log in."
        )

        return redirect("login")

    if default_token_generator.check_token(user, token):

        user.is_active = True
        user.save(update_fields=["is_active"])

        get_user_subscription(user)

        messages.success(
            request,
            "Your email has been verified successfully. "
            "You can now log in."
        )

        return redirect("login")

    messages.error(
        request,
        "Your verification link is invalid or has expired. "
        "Please request another one."
    )

    return redirect("resend_verification")


# =====================================================
# RESEND VERIFICATION EMAIL
# =====================================================

def resend_verification(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        email = request.POST.get("email", "").strip().lower()

        if not email:

            messages.error(request, "Please enter your email address.")

        else:

            user = User.objects.filter(
                email__iexact=email,
                is_active=False
            ).first()

            if user:

                try:
                    send_verification_email(request, user)

                except Exception:

                    messages.error(
                        request,
                        "We could not send the verification email. "
                        "Please try again later."
                    )

                    return show_page(
                        request,
                        "resend_verification"
                    )

            messages.success(
                request,
                "If an unverified account exists with that email, "
                "a verification link has been sent."
            )

            return redirect("login")

    return show_page(request, "resend_verification")


# =====================================================
# FORGOT PASSWORD
# =====================================================

def forgot_password(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        email = request.POST.get("email", "").strip().lower()

        if not email:

            messages.error(request, "Please enter your email address.")

        else:

            user = User.objects.filter(
                email__iexact=email,
                is_active=True
            ).first()

            if user:

                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)

                reset_url = request.build_absolute_uri(
                    reverse(
                        "reset_password",
                        kwargs={
                            "uidb64": uid,
                            "token": token
                        }
                    )
                )

                subject = "Reset your ClearanceVault password"

                message = f"""
Hello {user.first_name},

We received a request to reset your ClearanceVault password.

Click this link to create a new password:

{reset_url}

Your reset link expires after 24 hours.

If you did not request this, ignore this email.

ClearanceVault Team
"""

                try:

                    send_account_email(
                        subject,
                        message,
                        user.email
                    )

                except Exception:

                    messages.error(
                        request,
                        "We could not send the password reset email. "
                        "Please try again later."
                    )

                    return show_page(request, "forgot_password")

            messages.success(
                request,
                "If an active account exists with that email, "
                "a password-reset link has been sent."
            )

            return redirect("login")

    return show_page(request, "forgot_password")


# =====================================================
# RESET PASSWORD
# =====================================================

def reset_password(request, uidb64, token):

    try:

        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)

    except (
        TypeError,
        ValueError,
        OverflowError,
        User.DoesNotExist
    ):

        user = None

    if user is None or not user.is_active:

        messages.error(
            request,
            "This password-reset link is invalid or has expired."
        )

        return redirect("forgot_password")

    if not default_token_generator.check_token(user, token):

        messages.error(
            request,
            "This password-reset link is invalid or has expired."
        )

        return redirect("forgot_password")

    if request.method == "POST":

        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        if not password1 or not password2:

            messages.error(
                request,
                "Please complete both password fields."
            )

        elif password1 != password2:

            messages.error(
                request,
                "Your passwords do not match."
            )

        else:

            try:

                validate_password(password1, user=user)

                user.set_password(password1)
                user.save()

                messages.success(
                    request,
                    "Your password has been changed successfully. "
                    "You can now log in."
                )

                return redirect("login")

            except ValidationError as error:

                for error_message in error.messages:
                    messages.error(request, error_message)

    return show_page(request, "reset_password")


# =====================================================
# DASHBOARD
# =====================================================

@login_required
def dashboard(request):

    documents = Document.objects.filter(owner=request.user)
    checklist = ClearanceItem.objects.filter(owner=request.user)

    subscription = get_user_subscription(request.user)

    total_items = checklist.count()
    completed_items = checklist.filter(completed=True).count()

    progress = (
        round(completed_items / total_items * 100)
        if total_items else 0
    )

    storage_used = get_storage_used(request.user)
    storage_limit = subscription.storage_limit

    storage_percent = (
        min(round(storage_used / storage_limit * 100), 100)
        if storage_limit else 0
    )

    return show_page(
        request,
        "dashboard",
        document_count=documents.count(),
        recent_documents=documents[:5],
        total_items=total_items,
        completed_items=completed_items,
        progress=progress,
        subscription=subscription,
        storage_used=storage_used,
        storage_limit=storage_limit,
        storage_percent=storage_percent,
        storage_used_mb=round(storage_used / (1024 * 1024), 2),
        storage_limit_mb=round(storage_limit / (1024 * 1024), 2),
    )


# =====================================================
# DOCUMENT MANAGER
# =====================================================

@login_required
def documents(request):

    if request.method == "POST":

        title = request.POST.get("title", "").strip()
        category = request.POST.get("category", "other")
        uploaded_file = request.FILES.get("file")

        allowed_extensions = {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg"
        }

        valid_categories = {
            "admission",
            "academic",
            "identity",
            "clearance",
            "other"
        }

        if not title or not uploaded_file:

            messages.error(
                request,
                "Enter a document name and select a file."
            )

        elif category not in valid_categories:

            messages.error(request, "Invalid document category.")

        elif Path(uploaded_file.name).suffix.lower() not in allowed_extensions:

            messages.error(
                request,
                "Only PDF, PNG and JPG files are allowed."
            )

        elif uploaded_file.size > 10 * 1024 * 1024:

            messages.error(
                request,
                "Maximum file size is 10 MB."
            )

        else:

            subscription = get_user_subscription(request.user)
            storage_used = get_storage_used(request.user)

            if storage_used + uploaded_file.size > subscription.storage_limit:

                messages.error(
                    request,
                    "You have reached your storage limit. "
                    "Upgrade your plan to get more storage."
                )

            else:

                Document.objects.create(
                    owner=request.user,
                    title=title,
                    category=category,
                    file=uploaded_file
                )

                messages.success(
                    request,
                    "Document uploaded successfully."
                )

                return redirect("documents")

    all_documents = Document.objects.filter(owner=request.user)

    return show_page(
        request,
        "documents",
        documents=all_documents
    )


# =====================================================
# DOWNLOAD DOCUMENT
# =====================================================

@login_required
def download_document(request, document_id):

    document = get_object_or_404(
        Document,
        id=document_id,
        owner=request.user
    )

    try:

        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=Path(document.file.name).name
        )

    except (FileNotFoundError, ValueError, OSError):

        raise Http404("Document not found.")


# =====================================================
# DELETE DOCUMENT
# =====================================================

@login_required
@require_POST
def delete_document(request, document_id):

    document = get_object_or_404(
        Document,
        id=document_id,
        owner=request.user
    )

    document.file.delete(save=False)
    document.delete()

    messages.success(
        request,
        "Document deleted successfully."
    )

    return redirect("documents")


# =====================================================
# CLEARANCE CHECKLIST
# =====================================================

@login_required
def clearance(request):

    if request.method == "POST":

        title = request.POST.get("title", "").strip()

        if title:

            ClearanceItem.objects.create(
                owner=request.user,
                title=title
            )

            messages.success(request, "Clearance item added.")

        else:

            messages.error(request, "Enter a clearance item.")

        return redirect("clearance")

    items = ClearanceItem.objects.filter(owner=request.user)

    total = items.count()
    done = items.filter(completed=True).count()

    progress = round(done / total * 100) if total else 0

    return show_page(
        request,
        "clearance",
        items=items,
        total=total,
        done=done,
        progress=progress
    )


# =====================================================
# TOGGLE CLEARANCE ITEM
# =====================================================

@login_required
@require_POST
def toggle_clearance(request, item_id):

    item = get_object_or_404(
        ClearanceItem,
        id=item_id,
        owner=request.user
    )

    item.completed = not item.completed
    item.save(update_fields=["completed"])

    return redirect("clearance")


# =====================================================
# DELETE CLEARANCE ITEM
# =====================================================

@login_required
@require_POST
def delete_clearance(request, item_id):

    item = get_object_or_404(
        ClearanceItem,
        id=item_id,
        owner=request.user
    )

    item.delete()

    messages.success(request, "Clearance item deleted.")

    return redirect("clearance")


# =====================================================
# SHARED FILES
# =====================================================

@login_required
def shared_files(request):

    sent_files = SharedDocument.objects.filter(
        sender=request.user,
        revoked=False
    ).select_related(
        "document",
        "recipient"
    )

    received_files = SharedDocument.objects.filter(
        recipient=request.user,
        revoked=False
    ).select_related(
        "document",
        "sender"
    )

    return show_page(
        request,
        "shared",
        sent_files=sent_files,
        received_files=received_files
    )


# =====================================================
# SHARE A DOCUMENT
# =====================================================

@login_required
@require_POST
def share_document(request, document_id):

    document = get_object_or_404(
        Document,
        id=document_id,
        owner=request.user
    )

    email = request.POST.get("email", "").strip().lower()

    if not email:

        messages.error(
            request,
            "Enter the recipient's email address."
        )

        return redirect("shared")

    recipient = User.objects.filter(
        email__iexact=email,
        is_active=True
    ).first()

    if not recipient:

        messages.error(
            request,
            "No active ClearanceVault account was found with that email."
        )

        return redirect("shared")

    if recipient.pk == request.user.pk:

        messages.error(
            request,
            "You cannot share a document with yourself."
        )

        return redirect("shared")

    share, created = SharedDocument.objects.get_or_create(
        document=document,
        recipient=recipient,
        defaults={
            "sender": request.user,
            "revoked": False
        }
    )

    if not created:

        if share.revoked:

            share.revoked = False
            share.sender = request.user

            share.save(update_fields=["revoked", "sender"])

            messages.success(
                request,
                "Document sharing has been restored."
            )

        else:

            messages.info(
                request,
                "This document has already been shared with that user."
            )

    else:

        messages.success(
            request,
            f"Document shared successfully with {recipient.email}."
        )

    return redirect("shared")


# =====================================================
# REVOKE SHARED DOCUMENT ACCESS
# =====================================================

@login_required
@require_POST
def revoke_shared_document(request, share_id):

    share = get_object_or_404(
        SharedDocument,
        id=share_id,
        sender=request.user
    )

    share.revoked = True
    share.save(update_fields=["revoked"])

    messages.success(
        request,
        "Access to this shared document has been revoked."
    )

    return redirect("shared")


# =====================================================
# DOWNLOAD A SHARED DOCUMENT
# =====================================================

@login_required
def download_shared_document(request, share_id):

    share = get_object_or_404(
        SharedDocument.objects.select_related("document"),
        id=share_id,
        recipient=request.user,
        revoked=False
    )

    document = share.document

    try:

        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=Path(document.file.name).name
        )

    except (FileNotFoundError, ValueError, OSError):

        raise Http404("Shared document not found.")


# =====================================================
# PROFILE
# =====================================================

@login_required
def profile(request):

    if request.method == "POST":

        name = request.POST.get("name", "").strip()

        if name:

            parts = name.split()

            request.user.first_name = parts[0]
            request.user.last_name = " ".join(parts[1:])

            request.user.save()

            messages.success(
                request,
                "Profile updated successfully."
            )

            return redirect("profile")

        messages.error(request, "Please enter your name.")

    return show_page(request, "profile")


# =====================================================
# LOGOUT
# =====================================================

@login_required
@require_POST
def logout_user(request):

    logout(request)

    return redirect("home")


# =====================================================
# PAYSTACK API HELPER
# =====================================================

def paystack_headers():

    if not settings.PAYSTACK_SECRET_KEY:
        raise ValueError("Paystack secret key is not configured.")

    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


# =====================================================
# INITIALIZE PAYSTACK SUBSCRIPTION PAYMENT
# =====================================================

@login_required
@require_POST
def initialize_subscription(request):

    plan = request.POST.get("plan", "").strip().lower()

    if plan not in ("plus", "pro"):

        messages.error(request, "Please select a valid subscription plan.")
        return redirect("dashboard")

    plan_code = settings.PAYSTACK_PLAN_CODES.get(plan)
    amount = settings.PAYSTACK_PLAN_AMOUNTS.get(plan)

    if not plan_code or not amount:

        messages.error(request, "This subscription plan is not configured.")
        return redirect("dashboard")

    if not request.user.email:

        messages.error(request, "Your account needs a valid email address.")
        return redirect("profile")

    reference = f"CV-{uuid.uuid4().hex}"

    payment = PaymentTransaction.objects.create(
        user=request.user,
        plan=plan,
        amount_kobo=amount,
        reference=reference,
        status="pending",
    )

    payload = {
        "email": request.user.email,
        "amount": amount,
        "plan": plan_code,
        "reference": reference,
        "callback_url": request.build_absolute_uri(
            reverse("paystack_callback")
        ),
        "metadata": {
            "user_id": request.user.pk,
            "plan": plan,
            "reference": reference,
            "product": "ClearanceVault",
        },
    }

    try:

        response = requests.post(
            f"{settings.PAYSTACK_BASE_URL}/transaction/initialize",
            headers=paystack_headers(),
            json=payload,
            timeout=settings.PAYSTACK_TIMEOUT,
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("status"):
            raise ValueError("Paystack could not initialize the payment.")

        authorization_url = result.get("data", {}).get("authorization_url")

        if not authorization_url:
            raise ValueError("Paystack did not return a checkout URL.")

        return redirect(authorization_url)

    except (requests.RequestException, ValueError) as error:

        payment.status = "failed"
        payment.gateway_response = {"error": str(error)}

        payment.save(
            update_fields=["status", "gateway_response"]
        )

        logger.exception("Paystack initialization failed.")

        messages.error(
            request,
            "We could not start your payment. Please try again."
        )

        return redirect("dashboard")


# =====================================================
# VERIFY PAYSTACK TRANSACTION
# =====================================================

@login_required
def paystack_callback(request):

    reference = request.GET.get("reference")

    if not reference:

        messages.error(request, "Payment reference is missing.")
        return redirect("dashboard")

    payment = get_object_or_404(
        PaymentTransaction,
        reference=reference,
        user=request.user,
    )

    if payment.status == "success":

        messages.success(
            request,
            "Your subscription payment has already been confirmed."
        )

        return redirect("dashboard")

    try:

        response = requests.get(
            f"{settings.PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=paystack_headers(),
            timeout=settings.PAYSTACK_TIMEOUT,
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("status"):
            raise ValueError("Paystack could not verify this transaction.")

        data = result.get("data", {})

        verified_amount = int(data.get("amount", 0))
        verified_currency = data.get("currency")
        verified_status = data.get("status")

        customer_email = (
            (data.get("customer") or {}).get("email", "").lower()
        )

        if verified_status != "success":

            if verified_status == "failed":

                payment.status = "failed"
                payment.gateway_response = data

                payment.save(
                    update_fields=["status", "gateway_response"]
                )

            messages.warning(
                request,
                "Your payment has not been confirmed as successful."
            )

            return redirect("dashboard")

        if verified_amount != payment.amount_kobo:
            raise ValueError("The verified payment amount does not match.")

        if verified_currency != "NGN":
            raise ValueError("The payment currency is incorrect.")

        if customer_email != request.user.email.lower():
            raise ValueError("The payment email does not match your account.")

        with transaction.atomic():

            payment = PaymentTransaction.objects.select_for_update().get(
                pk=payment.pk
            )

            if payment.status != "success":

                paid_at = (
                    parse_datetime(data.get("paid_at", ""))
                    or timezone.now()
                )

                payment.status = "success"
                payment.gateway_response = data
                payment.paid_at = paid_at

                payment.save(
                    update_fields=[
                        "status",
                        "gateway_response",
                        "paid_at",
                    ]
                )

                subscription, created = (
                    UserSubscription.objects.select_for_update().get_or_create(
                        user=request.user,
                        defaults={
                            "plan": "free",
                            "status": "active",
                        }
                    )
                )

                subscription.plan = payment.plan
                subscription.status = "active"
                subscription.current_period_start = paid_at

                customer = data.get("customer") or {}
                subscription_data = data.get("subscription") or {}

                if isinstance(customer, dict):

                    subscription.paystack_customer_code = (
                        customer.get("customer_code")
                        or subscription.paystack_customer_code
                    )

                if isinstance(subscription_data, dict):

                    subscription.paystack_subscription_code = (
                        subscription_data.get("subscription_code")
                        or subscription.paystack_subscription_code
                    )

                    subscription.paystack_email_token = (
                        subscription_data.get("email_token")
                        or subscription.paystack_email_token
                    )

                    next_payment = subscription_data.get("next_payment_date")

                    if next_payment:

                        subscription.next_payment_date = (
                            parse_datetime(next_payment)
                        )

                subscription.save()

        messages.success(
            request,
            f"Your ClearanceVault {payment.plan.title()} payment "
            "was verified successfully!"
        )

    except (requests.RequestException, ValueError) as error:

        logger.exception(
            "Paystack transaction verification failed: %s",
            error
        )

        messages.error(
            request,
            "We could not confirm your payment. "
            "If you were charged, please contact support."
        )

    return redirect("dashboard")
