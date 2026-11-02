
from django.conf import settings
from django.db import models


# =====================================================
# DOCUMENTS
# =====================================================

class Document(models.Model):

    CATEGORY_CHOICES = [
        ("admission", "Admission"),
        ("academic", "Academic"),
        ("identity", "Identity"),
        ("clearance", "Clearance"),
        ("other", "Other"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    title = models.CharField(max_length=150)

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="other"
    )

    file = models.FileField(
        upload_to="student_documents/%Y/%m/"
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


# =====================================================
# CLEARANCE CHECKLIST
# =====================================================

class ClearanceItem(models.Model):

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="clearance_items"
    )

    title = models.CharField(max_length=160)

    completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.title


# =====================================================
# USER SUBSCRIPTIONS
# =====================================================

class UserSubscription(models.Model):

    PLAN_CHOICES = [
        ("free", "Free"),
        ("plus", "Plus"),
        ("pro", "Pro"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("past_due", "Payment overdue"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription"
    )

    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default="free"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    current_period_start = models.DateTimeField(
        null=True,
        blank=True
    )

    current_period_end = models.DateTimeField(
        null=True,
        blank=True
    )

    paystack_customer_code = models.CharField(
        max_length=150,
        blank=True
    )

    paystack_subscription_code = models.CharField(
        max_length=150,
        blank=True
    )

    # Required by Paystack when managing subscription cancellation.
    paystack_email_token = models.CharField(
        max_length=255,
        blank=True
    )

    # Tracks the next expected subscription payment.
    next_payment_date = models.DateTimeField(
        null=True,
        blank=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    STORAGE_LIMITS = {
        "free": 100 * 1024 * 1024,
        "plus": 1024 * 1024 * 1024,
        "pro": 5 * 1024 * 1024 * 1024,
    }

    @property
    def storage_limit(self):
        return self.STORAGE_LIMITS.get(
            self.plan,
            self.STORAGE_LIMITS["free"]
        )

    def __str__(self):
        return f"{self.user} - {self.plan}"


# =====================================================
# PAYSTACK PAYMENT RECORDS
# =====================================================

class PaymentTransaction(models.Model):

    PLAN_CHOICES = [
        ("plus", "Plus"),
        ("pro", "Pro"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Successful"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_transactions"
    )

    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES
    )

    amount_kobo = models.PositiveIntegerField()

    reference = models.CharField(
        max_length=150,
        unique=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    gateway_response = models.JSONField(
        default=dict,
        blank=True
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.plan} - {self.reference}"


# =====================================================
# FILE SHARING BETWEEN USERS
# =====================================================

class SharedDocument(models.Model):

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="shares"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_shares"
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_shares"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["document", "recipient"],
                name="unique_document_recipient_share"
            )
        ]

    def __str__(self):
        return f"{self.document.title}: {self.sender} to {self.recipient}"


# =====================================================
# PAYSTACK WEBHOOK EVENT TRACKING
# =====================================================

class PaystackWebhookEvent(models.Model):

    event_hash = models.CharField(
        max_length=64,
        unique=True
    )

    event_type = models.CharField(
        max_length=100
    )

    payload = models.JSONField(
        default=dict,
        blank=True
    )

    processed = models.BooleanField(default=False)

    received_at = models.DateTimeField(auto_now_add=True)

    processed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.event_type} - {self.event_hash[:12]}"
