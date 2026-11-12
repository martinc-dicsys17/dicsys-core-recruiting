from decimal import Decimal

from backend.core.llm import LLMResult
from backend.core.storage import StorageBackend


class FakeEmailService:
    def __init__(self):
        self.messages = []

    def configure(self, api_key, default_from=None):
        return None

    def send(
        self,
        to,
        subject,
        html,
        from_email=None,
        reply_to=None,
    ):
        message = {
            "to": to,
            "subject": subject,
            "html": html,
            "from_email": from_email,
            "reply_to": reply_to,
        }
        self.messages.append(message)
        return {
            "status_code": 202,
            "message_id": f"fake-email-{len(self.messages)}",
        }

    def send_from_schema(self, email):
        return self.send(
            to=email.to,
            subject=email.subject,
            html=email.html,
            from_email=email.from_email,
            reply_to=email.reply_to,
        )


class FakeWebexService:
    def __init__(self):
        self.messages = []
        self.personas = set()  # emails con cuenta de Webex
        self.busquedas = []

    def existe_persona(self, email, timeout=10.0):
        self.busquedas.append(email)
        return email.strip().lower() in self.personas

    @property
    def is_configured(self):
        return True

    def configure(self, bot_token, default_room_id=None):
        return None

    def send_text(self, text, **destination):
        message = {
            "kind": "text",
            "text": text,
            **destination,
        }
        self.messages.append(message)
        return {
            "success": True,
            "message_id": f"fake-webex-{len(self.messages)}",
            "status_code": 200,
        }

    def send_card(self, card, fallback_text="Card", **destination):
        message = {
            "kind": "card",
            "card": card,
            "text": fallback_text,
            **destination,
        }
        self.messages.append(message)
        return {
            "success": True,
            "message_id": f"fake-webex-{len(self.messages)}",
            "status_code": 200,
        }

    def send_message(self, message):
        destination = {
            "room_id": message.room_id,
            "person_email": message.person_email,
            "person_id": message.person_id,
        }
        if message.adaptive_card:
            return self.send_card(
                message.adaptive_card,
                fallback_text=message.text,
                **destination,
            )
        return self.send_text(
            message.text,
            markdown=message.markdown,
            **destination,
        )

    # ── Membresías (team + espacios) ──────────────────────────────────────────

    def list_rooms_by_team(self, team_id, timeout=15.0):
        return {"success": True, "rooms": getattr(self, "rooms", [])}

    def list_room_member_emails(self, room_id, timeout=15.0):
        return {"success": True, "emails": set()}

    def list_team_member_emails(self, team_id, timeout=15.0):
        return {"success": True, "emails": set()}

    def ensure_membership(self, room_id, person_email):
        self.messages.append({"kind": "membership", "room_id": room_id, "person_email": person_email})
        return {"success": True, "added": True}

    def ensure_team_membership(self, team_id, person_email):
        self.messages.append({"kind": "team_membership", "team_id": team_id, "person_email": person_email})
        return {"success": True, "added": True}


class InMemoryStorageBackend(StorageBackend):
    def __init__(self):
        self.files = {}

    def upload(self, key, content, content_type="application/octet-stream"):
        self.files[key] = {
            "content": content,
            "content_type": content_type,
        }
        return key

    def download(self, key):
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]["content"]

    def delete(self, key):
        return self.files.pop(key, None) is not None

    def exists(self, key):
        return key in self.files

    def get_url(self, key, expires=3600):
        return f"/storage/{key}"


class FakeLLMGenerator:
    def __init__(self, text="OK"):
        self.text = text
        self.calls = []

    def __call__(
        self,
        modulo,
        contents,
        model=None,
        db=None,
        usuario=None,
        **opciones,
    ):
        self.calls.append(
            {
                "modulo": modulo,
                "contents": contents,
                "model": model,
                "db": db,
                "usuario": usuario,
                "opciones": opciones,
            }
        )
        return LLMResult(
            id=f"fake-llm-{len(self.calls)}",
            modulo=modulo,
            model_name=model or "fake-model",
            text=self.text,
            tokens_input=1,
            tokens_output=1,
            tokens_total=2,
            costo_usd=Decimal("0"),
        )
