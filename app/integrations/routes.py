from flask import (
    Blueprint, flash, redirect, render_template, request, url_for,
)

from .. import current_app_config
from ..auth import role_required
from .. import models as m  # noqa: F401
from .amocrm import AmoCrmClient, AmoCrmError
from .ones import OneCClient, OneCError
from . import sync

integrations_bp = Blueprint("integrations", __name__)


def _amocrm_client():
    cfg = current_app_config()
    return AmoCrmClient(cfg["AMOCRM_URL"], cfg["AMOCRM_KEY"], cfg["AMOCRM_SECRET"])


def _ones_client():
    cfg = current_app_config()
    return OneCClient(cfg["ONES_URL"], cfg["ONES_USER"], cfg["ONES_PASS"])


@integrations_bp.route("/")
@role_required(m.ROLE_ADMIN)
def index():
    cfg = current_app_config()
    return render_template(
        "integrations.html",
        amocrm_configured=bool(cfg["AMOCRM_URL"] and cfg["AMOCRM_KEY"]),
        ones_configured=bool(cfg["ONES_URL"]),
        leads_count=m.Lead.query.count(),
    )


@integrations_bp.route("/run/<name>", methods=["POST"])
@role_required(m.ROLE_ADMIN)
def run(name):
    try:
        if name == "amocrm_leads":
            result = sync.sync_amocrm_leads(_amocrm_client(),
                                            current_app_config()["AMOCRM_PIPELINE_ID"])
        elif name == "ones_products":
            result = sync.sync_1c_products(_ones_client(),
                                           current_app_config()["ONES_CATALOG_PATH"])
        elif name == "ones_stocks":
            result = sync.sync_1c_stocks(_ones_client(),
                                         current_app_config()["ONES_STOCKS_PATH"])
        else:
            flash("Неизвестная синхронизация", "error")
            return redirect(url_for("integrations.index"))
        flash(f'{result["source"]}: создано {result.get("created", 0)}, '
              f'обновлено {result.get("updated", 0)}, ошибок {len(result["errors"])}',
              "success" if not result["errors"] else "warning")
        for err in result["errors"][:3]:
            flash(err, "error")
    except (AmoCrmError, OneCError) as e:
        flash(f"Ошибка интеграции: {e}", "error")
    except Exception as e:  # noqa: BLE001
        flash(f"Не настроено или недоступно: {e}", "error")
    return redirect(url_for("integrations.index"))
