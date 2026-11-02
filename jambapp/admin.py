
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

from .models import (
    Document,
    ClearanceItem,
    UserSubscription,
    PaymentTransaction,
    SharedDocument,
)


# =====================================
# USER SUBSCRIPTION INLINE
# =====================================

class UserSubscriptionInline(admin.StackedInline):
    model = UserSubscription
    can_delete = False
    extra = 0
    max_num = 1

    fields = (
        "plan",
        "status",
        "current_period_start",
        "current_period_end",
        "updated_at",
    )

    readonly_fields = ("updated_at",)


# =====================================
# CUSTOM USER ADMIN
# =====================================

admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    inlines = (UserSubscriptionInline,)

    list_display = (
        "id",
        "username",
        "email",
        "first_name",
        "last_name",
        "get_subscription_plan",
        "is_active",
        "is_staff",
        "date_joined",
    )

    list_display_links = ("username",)

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
    )

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
    )

    ordering = ("-date_joined",)

    list_per_page = 25

    readonly_fields = (
        "last_login",
        "date_joined",
    )

    fieldsets = (
        ("Account Information", {
            "fields": (
                "username",
                "password",
            )
        }),

        ("Personal Information", {
            "fields": (
                "first_name",
                "last_name",
                "email",
            )
        }),

        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),

        ("Important Dates", {
            "fields": (
                "last_login",
                "date_joined",
            )
        }),
    )

    @admin.display(description="Subscription Plan")
    def get_subscription_plan(self, obj):
        try:
            return obj.subscription.plan.upper()
        except UserSubscription.DoesNotExist:
            return "FREE"


# =====================================
# DOCUMENT ADMIN
# =====================================

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "owner",
        "category",
        "uploaded_at",
    )

    list_filter = ("category", "uploaded_at")

    search_fields = (
        "title",
        "owner__username",
        "owner__email",
    )

    readonly_fields = ("uploaded_at",)


# =====================================
# CLEARANCE CHECKLIST ADMIN
# =====================================

@admin.register(ClearanceItem)
class ClearanceItemAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "owner",
        "completed",
        "created_at",
    )

    list_filter = ("completed", "created_at")

    search_fields = (
        "title",
        "owner__username",
        "owner__email",
    )

    readonly_fields = ("created_at",)


# =====================================
# SUBSCRIPTION ADMIN
# =====================================

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "plan",
        "status",
        "current_period_start",
        "current_period_end",
        "updated_at",
    )

    list_filter = ("plan", "status")

    search_fields = (
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "paystack_customer_code",
        "paystack_subscription_code",
        "updated_at",
    )


# =====================================
# PAYMENT TRANSACTION ADMIN
# =====================================

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):

    list_display = (
        "reference",
        "user",
        "plan",
        "amount_kobo",
        "status",
        "created_at",
        "paid_at",
    )

    list_filter = (
        "status",
        "plan",
        "created_at",
    )

    search_fields = (
        "reference",
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "user",
        "plan",
        "amount_kobo",
        "reference",
        "status",
        "gateway_response",
        "paid_at",
        "created_at",
    )

    def has_add_permission(self, request):
        return False


# =====================================
# SHARED DOCUMENT ADMIN
# =====================================

@admin.register(SharedDocument)
class SharedDocumentAdmin(admin.ModelAdmin):

    list_display = (
        "document",
        "sender",
        "recipient",
        "revoked",
        "created_at",
    )

    list_filter = ("revoked", "created_at")

    search_fields = (
        "document__title",
        "sender__username",
        "recipient__username",
        "sender__email",
        "recipient__email",
    )

    readonly_fields = ("created_at",)
