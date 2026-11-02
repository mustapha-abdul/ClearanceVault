from django.urls import path
from . import views


urlpatterns = [

    # HOME
    path("", views.home, name="home"),

    # AUTHENTICATION
    path("register/", views.register, name="register"),
    path("login/", views.login_page, name="login"),
    path("logout/", views.logout_user, name="logout"),

    # EMAIL VERIFICATION
    path(
        "verify-email/<uidb64>/<token>/",
        views.verify_email,
        name="verify_email"
    ),
    path(
        "resend-verification/",
        views.resend_verification,
        name="resend_verification"
    ),

    # PASSWORD RESET
    path(
        "forgot-password/",
        views.forgot_password,
        name="forgot_password"
    ),
    path(
        "reset-password/<uidb64>/<token>/",
        views.reset_password,
        name="reset_password"
    ),

    # DASHBOARD
    path("dashboard/", views.dashboard, name="dashboard"),

    # DOCUMENTS
    path("documents/", views.documents, name="documents"),
    path(
        "documents/download/<int:document_id>/",
        views.download_document,
        name="download_document"
    ),
    path(
        "documents/delete/<int:document_id>/",
        views.delete_document,
        name="delete_document"
    ),
    path(
        "documents/share/<int:document_id>/",
        views.share_document,
        name="share_document"
    ),

    # ADMIN DASHBOARD
    path(
        "admin-dashboard/",
        views.admin_dashboard,
        name="admin_dashboard"
    ),
    path(
        "admin-dashboard/users/<int:user_id>/",
        views.admin_user_detail,
        name="admin_user_detail"
    ),
    path(
        "admin-dashboard/users/<int:user_id>/toggle-status/",
        views.admin_toggle_user_status,
        name="admin_toggle_user_status"
    ),
    path(
        "admin-dashboard/users/<int:user_id>/change-plan/",
        views.admin_change_user_plan,
        name="admin_change_user_plan"
    ),
    path(
        "admin-dashboard/users/<int:user_id>/delete/",
        views.admin_delete_user,
        name="admin_delete_user"
    ),

    # CLEARANCE CHECKLIST
    path("clearance/", views.clearance, name="clearance"),
    path(
        "clearance/toggle/<int:item_id>/",
        views.toggle_clearance,
        name="toggle_clearance"
    ),
    path(
        "clearance/delete/<int:item_id>/",
        views.delete_clearance,
        name="delete_clearance"
    ),

    # SHARED FILES
    path("shared/", views.shared_files, name="shared"),
    path(
        "shared/revoke/<int:share_id>/",
        views.revoke_shared_document,
        name="revoke_shared_document"
    ),
    path(
        "shared/download/<int:share_id>/",
        views.download_shared_document,
        name="download_shared_document"
    ),

    # PROFILE
    path("profile/", views.profile, name="profile"),

    # PAYSTACK PAYMENTS
    path(
        "payments/subscribe/",
        views.initialize_subscription,
        name="initialize_subscription"
    ),
    path(
        "payments/callback/",
        views.paystack_callback,
        name="paystack_callback"
    ),

]