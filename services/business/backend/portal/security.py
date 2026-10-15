from django.utils import timezone

from .models import AuditEvent, Module


def audit(actor, action, target="", result="success", changes=None):
    return AuditEvent.objects.create(actor=actor if actor and actor.is_authenticated else None,
        action=action, target=str(target)[:150], result=result, changes=changes or [])


def authorized_modules(user):
    return Module.objects.filter(role__user=user).distinct()


def is_business_manager(user):
    return (user.is_active and not user.must_change_password
            and user.roles.filter(code="general_manager").exists()
            and authorized_modules(user).filter(code="business", enabled=True).exists())


def can_use_department(user, code):
    """Local business capability only; objects, sources and legacy launches keep their grants."""
    if code not in {"product", "hr", "cost", "business", "finance"}:
        return False
    if not user.is_active or user.must_change_password:
        return False
    module_code = "business" if code == "finance" else code
    return (authorized_modules(user).filter(code=module_code, enabled=True).exists()
            or is_business_manager(user)
            and Module.objects.filter(code=module_code, enabled=True).exists())


def can_use_business(user):
    return (user.is_active and not user.must_change_password
            and authorized_modules(user).filter(code="business", enabled=True).exclude(status="pending").exists())


def can_use_assistant(user):
    """Shared conversation access grants no department business or document access."""
    if not user or not user.is_authenticated or not user.is_active or user.must_change_password:
        return False
    modules = authorized_modules(user).filter(enabled=True)
    if modules.filter(code__in=("product", "hr", "cost")).exists() or is_business_manager(user):
        return True
    from .business_models import BusinessLedgerGrant
    return (user.department_code == "finance" and Module.objects.filter(code="business", enabled=True).exists()
            and BusinessLedgerGrant.objects.filter(user=user, department="finance").exists())


def current_ticket_authorized(ticket):
    user = ticket.user
    mapping = ticket.mapping
    return (ticket.expires_at > timezone.now() and ticket.session_version == user.session_version
            and ticket.grant_version == user.grant_version
            and mapping.enabled and mapping.user_id == user.pk
            and mapping.external_user_id == ticket.external_user_id and can_use_business(user))
