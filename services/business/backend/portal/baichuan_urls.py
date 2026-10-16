from django.urls import path

from . import baichuan_api

urlpatterns = [
    path("companies/", baichuan_api.companies),
    path("companies/<str:company_id>/", baichuan_api.company),
]
