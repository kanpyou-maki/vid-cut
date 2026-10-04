"""/api/settings: ワークスペース全体の設定（残す発話の前後の余白）の読み書き。"""

from fastapi import APIRouter

from vidcut.api.deps import Services
from vidcut.api.envelope import Envelope, ok
from vidcut.api.inputs import SettingsIn
from vidcut.api.outputs import SettingsOut
from vidcut.api.presenters import to_settings

router = APIRouter()


@router.get("/api/settings")
def get_settings(services: Services) -> Envelope[SettingsOut]:
    return ok(to_settings(services.settings.view()))


@router.put("/api/settings")
def put_settings(body: SettingsIn, services: Services) -> Envelope[SettingsOut]:
    """余白を保存する。null なら既定値に戻す。次の書き出しと、開き直したプレビューから効く。"""
    if body.keep_padding is None:
        return ok(to_settings(services.settings.reset_keep_padding()))
    return ok(to_settings(services.settings.save_keep_padding(body.keep_padding.to_domain())))
