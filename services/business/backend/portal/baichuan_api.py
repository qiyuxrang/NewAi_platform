from functools import wraps

from rest_framework.decorators import api_view
from rest_framework.exceptions import ParseError, UnsupportedMediaType
from rest_framework.response import Response

from .baichuan_service import (BaichuanError, company_detail, company_for, duplicate_name_warning,
                              list_companies, save_company)
from .security import audit


def endpoint(function):
    @wraps(function)
    def wrapped(request, *args, **kwargs):
        try:
            return function(request, *args, **kwargs)
        except (ParseError, UnsupportedMediaType):
            error = BaichuanError("invalid_request", "请提交合法 JSON 对象。", errors={"payload": "JSON 格式无效。"})
        except BaichuanError as caught:
            error = caught
        audit(request.user, "baichuan_request", request.path, result="denied", changes=[error.code])
        return Response({"code": error.code, "detail": error.detail, "errors": error.errors}, status=error.status)
    return wrapped


@api_view(["GET", "POST"])
@endpoint
def companies(request):
    if request.method == "GET":
        result = list_companies(request.user, request.query_params)
        audit(request.user, "baichuan_list")
        return Response(result)
    company = save_company(request.user, request.data)
    return Response({**company_detail(company, request.user), "warnings": duplicate_name_warning(company)}, status=201)


@api_view(["GET", "PUT"])
@endpoint
def company(request, company_id):
    if request.method == "GET":
        row = company_for(request.user, company_id)
        audit(request.user, "baichuan_read", row.pk)
        return Response(company_detail(row, request.user))
    row = save_company(request.user, request.data, company_id=company_id)
    return Response({**company_detail(row, request.user), "warnings": duplicate_name_warning(row)})
