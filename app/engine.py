import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .text import normalize, tokens

BRT = timezone(timedelta(hours=-3))
MAX_HISTORY = 6
MAX_AI_CALLS = 15

MENU = (
    "Posso te ajudar com:\n"
    "1. Tirar uma dúvida (convênios, valores, horários)\n"
    "2. Pedir um horário de consulta\n"
    "3. Falar com a recepção"
)
GREETING = "Oi! Aqui é o atendimento virtual da Odonto Prado."
HANDOFF = "Certo, avisei a recepção. Alguém da equipe continua a conversa por aqui em até 1 hora útil (seg a sex, 8h às 19h; sáb, 8h às 12h)."
WAITING_HUMAN = "Sua conversa já está com a recepção, é só aguardar. Se quiser voltar pro atendimento automático, digite menu."

PROCEDURES = {
    "1": "Avaliação",
    "2": "Limpeza",
    "3": "Clareamento",
    "4": "Aparelho",
    "5": "Dor ou urgência",
}
PROCEDURE_WORDS = {
    "avaliacao": "1", "consulta": "1", "orcamento": "1",
    "limpeza": "2", "tartaro": "2",
    "clareamento": "3", "clarear": "3",
    "aparelho": "4", "ortodontia": "4", "alinhador": "4",
    "dor": "5", "urgencia": "5", "quebrou": "5", "inchado": "5", "inchaco": "5",
}
WEEKDAYS = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}
WEEKDAY_NAMES = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

BOOKING_WORDS = {"marcar", "agendar", "agendamento", "agenda", "horario vago", "encaixe", "vaga"}
HUMAN_WORDS = {"atendente", "humano", "pessoa", "recepcao", "recepcionista", "falar com alguem", "falar com uma pessoa"}
RESET_WORDS = {"menu", "inicio", "voltar", "sair", "cancelar"}
YES = {"sim", "s", "isso", "confirmo", "confirmar", "pode", "ok", "certo"}
NO = {"nao", "n", "errado", "corrigir"}


@dataclass
class Reply:
    messages: list[str]
    state: dict
    handoff: bool = False
    mode: str = "regras"
    request: dict | None = field(default=None)


def _has_any(text: str, words: set[str]) -> bool:
    padded = f" {text} "
    return any(f" {w} " in padded for w in words)


def parse_day(text: str, today: date) -> date | None:
    n = normalize(text)
    if "hoje" in n.split():
        return today
    if "amanha" in n.split():
        return today + timedelta(days=1)

    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})\b", text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        for year in (today.year, today.year + 1):
            try:
                candidate = date(year, month, day)
            except ValueError:
                return None
            if candidate >= today:
                return candidate
        return None

    for word in n.split():
        key = word.replace("feira", "")
        if key in WEEKDAYS:
            ahead = (WEEKDAYS[key] - today.weekday()) % 7 or 7
            return today + timedelta(days=ahead)
    return None


class Engine:
    def __init__(self, answerer, today=None):
        self.answerer = answerer
        self._today = today

    def today(self) -> date:
        return self._today() if self._today else datetime.now(BRT).date()

    def handle(self, text: str, state: dict | None) -> Reply:
        state = dict(state or {})
        state.setdefault("step", "new")
        state.setdefault("data", {})
        state.setdefault("history", [])
        state.setdefault("ai_calls", 0)

        n = normalize(text)
        reply = self._route(text, n, state)
        self._remember(state, text, reply.messages)
        return reply

    def _route(self, text: str, n: str, state: dict) -> Reply:
        step = state["step"]

        if n in RESET_WORDS:
            state.update(step="menu", data={})
            return Reply([MENU], state)

        if step == "human":
            return Reply([WAITING_HUMAN], state, handoff=True)

        if _has_any(n, HUMAN_WORDS) or (step in ("new", "menu") and n == "3"):
            state["step"] = "human"
            return Reply([HANDOFF], state, handoff=True)

        if step.startswith("book_"):
            return self._booking(text, n, state)

        if _has_any(n, BOOKING_WORDS) or (step in ("new", "menu") and n == "2"):
            state.update(step="book_name", data={})
            return Reply(["Vamos lá. Qual o nome completo do paciente?"], state)

        if step in ("new", "menu") and n == "1":
            state["step"] = "faq"
            return Reply(["Pode mandar sua dúvida."], state)

        if not tokens(text):
            state["step"] = "menu"
            return Reply([GREETING, MENU] if step == "new" else [MENU], state)

        return self._faq(text, state)

    def _faq(self, text: str, state: dict) -> Reply:
        answerer = self.answerer
        if getattr(answerer, "mode", "") == "ia" and state["ai_calls"] >= MAX_AI_CALLS:
            answerer = answerer.fallback
        if getattr(answerer, "mode", "") == "ia":
            state["ai_calls"] += 1

        answer = answerer.answer(text, state["history"])
        state["step"] = "faq"
        messages = [answer.text]
        if answer.found:
            messages.append("Posso ajudar com mais alguma coisa? Se quiser marcar, digite 2.")
        return Reply(messages, state, mode=answer.mode)

    def _booking(self, text: str, n: str, state: dict) -> Reply:
        step, data = state["step"], state["data"]

        if step == "book_name":
            name = " ".join(text.split())
            if not re.fullmatch(r"[A-Za-zÀ-ÿ' ]{3,60}", name) or len(name.split()) < 2:
                return Reply(["Me manda o nome e o sobrenome, por favor (só letras)."], state)
            data["name"] = " ".join(w if w.lower() in ("da", "de", "do", "das", "dos", "e") else w.capitalize() for w in name.lower().split())
            state["step"] = "book_procedure"
            options = "\n".join(f"{k}. {v}" for k, v in PROCEDURES.items())
            return Reply([f"Obrigado, {data['name'].split()[0]}. Qual o motivo da consulta?\n{options}"], state)

        if step == "book_procedure":
            choice = n if n in PROCEDURES else next((PROCEDURE_WORDS[w] for w in n.split() if w in PROCEDURE_WORDS), None)
            if not choice:
                return Reply(["Não entendi. Responde com o número de 1 a 5."], state)
            data["procedure"] = PROCEDURES[choice]
            if choice == "5":
                state["step"] = "human"
                request = dict(data, urgent=True)
                return Reply([
                    "Entendi, é urgência. Já avisei a recepção pra tentar um encaixe hoje.",
                    "Se tiver inchaço no rosto com febre ou dificuldade pra respirar ou engolir, vá direto a um pronto-socorro.",
                ], state, handoff=True, request=request)
            state["step"] = "book_day"
            return Reply(["Qual dia você prefere? Pode ser uma data (ex: 25/09) ou dia da semana."], state)

        if step == "book_day":
            day = parse_day(text, self.today())
            if day is None or day < self.today():
                return Reply(["Não consegui entender a data. Tenta assim: 25/09, amanhã ou sexta."], state)
            if day.weekday() == 6:
                return Reply(["Domingo a clínica fica fechada. Escolhe outro dia?"], state)
            if (day - self.today()).days > 60:
                return Reply(["A agenda abre com até 60 dias de antecedência. Escolhe uma data mais próxima?"], state)
            data["day"] = day.isoformat()
            state["step"] = "book_period"
            if day.weekday() == 5:
                data["period"] = "manhã"
                return self._confirm(state)
            return Reply(["Prefere de manhã ou à tarde?"], state)

        if step == "book_period":
            if "manha" in n.split() or n == "1":
                data["period"] = "manhã"
            elif "tarde" in n.split() or "noite" in n.split() or n == "2":
                data["period"] = "tarde"
            else:
                return Reply(["Responde manhã ou tarde, por favor."], state)
            return self._confirm(state)

        if step == "book_confirm":
            words = set(n.split())
            if words & YES and not words & NO:
                state["step"] = "human"
                return Reply([
                    "Pedido enviado. A recepção confere a agenda e confirma o horário exato por aqui.",
                    "Lembrando: traga um documento com foto e, se for convênio, a carteirinha.",
                ], state, handoff=True, request=dict(data))
            if words & NO:
                state.update(step="book_name", data={})
                return Reply(["Sem problema, vamos de novo. Qual o nome completo do paciente?"], state)
            return Reply(["Responde sim pra confirmar ou não pra corrigir."], state)

        state.update(step="menu", data={})
        return Reply([MENU], state)

    def _confirm(self, state: dict) -> Reply:
        data = state["data"]
        day = date.fromisoformat(data["day"])
        state["step"] = "book_confirm"
        summary = (
            f"Confere se está certo:\n"
            f"Paciente: {data['name']}\n"
            f"Motivo: {data['procedure']}\n"
            f"Dia: {WEEKDAY_NAMES[day.weekday()]}, {day.strftime('%d/%m')}, de {data['period']}\n"
            "Posso enviar o pedido? (sim ou não)"
        )
        return Reply([summary], state)

    def _remember(self, state: dict, text: str, messages: list[str]) -> None:
        history = state["history"]
        history.append({"role": "user", "content": text[:500]})
        history.append({"role": "assistant", "content": "\n".join(messages)[:700]})
        del history[:-MAX_HISTORY]
