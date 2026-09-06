from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import TestRun
from ..services import pdf_report
from ..services.audit import audit_chain
from ..services.reporting import build_report, markdown_report

router = APIRouter(tags=["reports"])


@router.get("/reports/latest")
def get_latest_report(format: str = "json", db: Session = Depends(get_db)):
    latest = db.query(TestRun).filter_by(status="completed").order_by(TestRun.id.desc()).first()
    if not latest:
        raise HTTPException(404, "No completed runs found")
    return get_report(latest.id, format=format, db=db)


@router.get("/reports/{run_id}")
def get_report(run_id: int | str, format: str = "json", db: Session = Depends(get_db)):
    """One report, three renderings: `json` (default), `md`, and `pdf`."""
    if str(run_id).lower() == "latest":
        latest = db.query(TestRun).filter_by(status="completed").order_by(TestRun.id.desc()).first()
        if not latest:
            raise HTTPException(404, "No completed runs found")
        run_id = latest.id
    else:
        try:
            run_id = int(run_id)
        except ValueError:
            raise HTTPException(400, "Invalid run_id")
    if not db.get(TestRun, run_id):
        raise HTTPException(404, "run not found")
    data = build_report(db, run_id)

    if format == "md":
        return PlainTextResponse(markdown_report(data), media_type="text/markdown")

    if format == "pdf":
        if not pdf_report.available():
            raise HTTPException(503, "PDF export requires reportlab — pip install reportlab")
        payload = pdf_report.render_pdf(data, audit=audit_chain.verify(db, run_id))
        return Response(
            content=payload,
            media_type="application/pdf",
            headers={"content-disposition": f'attachment; filename="sentinel-assessment-run-{run_id}.pdf"'},
        )

    data["audit"] = audit_chain.verify(db, run_id)
    return data
