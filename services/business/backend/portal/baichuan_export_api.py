from django.http import FileResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .baichuan_api import endpoint
from .baichuan_assistant_service import job_data
from .baichuan_exports import enqueue_export, open_export


@api_view(["POST"])
@endpoint
def exports(request, snapshot_id):
    job = enqueue_export(request.user, snapshot_id, request.data)
    return Response({"job": job_data(job)}, status=202)


@api_view(["GET"])
@endpoint
def download(request, export_id):
    export, stream = open_export(request.user, export_id)
    response = FileResponse(stream, as_attachment=True, filename=f"百川匹配结果-{export.snapshot.result_revision}.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
