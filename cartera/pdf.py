from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static


class PDFDependencyError(RuntimeError):
    pass


def _logo_uri(config):
    static_path = (getattr(config, "logo_static_path", "") or "icons/Logo.png").strip()
    candidate = Path(settings.BASE_DIR) / "static" / static_path
    if candidate.exists():
        return candidate.resolve().as_uri()
    return static(static_path)


def safe_pdf_filename(value):
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value))
    cleaned = cleaned.strip("_") or "documento"
    return f"{cleaned}.pdf"


def render_pdf_response(request, template_name, context, filename):
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise PDFDependencyError("WeasyPrint no esta instalado.") from exc

    context = dict(context)
    context["logo_uri"] = _logo_uri(context["config"])
    html = render(request, template_name, context).content.decode("utf-8")
    pdf = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{safe_pdf_filename(filename)}"'
    return response
