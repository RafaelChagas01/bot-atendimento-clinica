const list = document.getElementById('messages');
const form = document.getElementById('composer');
const input = document.getElementById('text');
const sendButton = document.getElementById('send');
const modeLabel = document.getElementById('mode');
const tickets = document.getElementById('tickets');
const deskEmpty = document.getElementById('desk-empty');

let state = null;
let busy = false;

const MODE_TEXT = {
  ia: 'respondendo com IA',
  offline: 'respondendo pela base da clínica',
  regras: 'atendimento automático',
};

function clock() {
  return new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function addBubble(text, who) {
  const item = document.createElement('li');
  item.className = `bubble ${who}`;
  item.textContent = text;
  if (who !== 'notice') {
    const time = document.createElement('time');
    time.textContent = clock();
    item.append(time);
  }
  list.append(item);
  list.scrollTop = list.scrollHeight;
}

function formatDay(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  const day = new Date(y, m - 1, d);
  return day.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: '2-digit' });
}

function addTicket(request) {
  const item = document.createElement('li');
  item.className = request.urgent ? 'ticket urgent' : 'ticket';

  const title = document.createElement('p');
  title.className = 'ticket-title';
  if (request.urgent) title.textContent = 'Urgência: encaixar hoje';
  else if (request.name) title.textContent = 'Pedido de consulta';
  else title.textContent = 'Paciente quer falar com alguém';
  item.append(title);

  const rows = [];
  if (request.name) rows.push(['Paciente', request.name]);
  if (request.procedure) rows.push(['Motivo', request.procedure]);
  if (request.day) rows.push(['Dia', formatDay(request.day)]);
  if (request.period) rows.push(['Período', request.period]);
  rows.push(['Recebido', clock()]);

  const dl = document.createElement('dl');
  for (const [label, value] of rows) {
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value;
    dl.append(dt, dd);
  }
  item.append(dl);

  tickets.prepend(item);
  deskEmpty.hidden = true;
}

async function send(text) {
  if (busy) return;
  busy = true;
  sendButton.disabled = true;
  addBubble(text, 'mine');

  const typing = document.createElement('li');
  typing.className = 'typing';
  typing.textContent = 'digitando...';
  list.append(typing);
  list.scrollTop = list.scrollHeight;

  const wasWithHuman = Boolean(state && list.dataset.human === '1');

  try {
    const res = await fetch('api/demo/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, state }),
    });
    typing.remove();

    if (res.status === 429) {
      addBubble('Muitas mensagens seguidas. Espera um minutinho e tenta de novo.', 'notice');
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    state = data.state;
    for (const message of data.messages) addBubble(message, 'theirs');
    modeLabel.textContent = MODE_TEXT[data.mode] || MODE_TEXT.regras;

    if (data.handoff && !wasWithHuman) {
      addTicket(data.request || {});
      addBubble('A conversa foi pra recepção. Veja no painel da recepção.', 'notice');
    }
    list.dataset.human = data.handoff ? '1' : '0';
  } catch (err) {
    typing.remove();
    addBubble('Não consegui responder agora. Tenta de novo em instantes.', 'notice');
    console.error(err);
  } finally {
    busy = false;
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = input.value.trim().slice(0, 500);
  if (!text) return;
  input.value = '';
  send(text);
});

document.getElementById('suggestions').addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (button) send(button.textContent);
});

document.getElementById('restart').addEventListener('click', () => {
  state = null;
  list.replaceChildren();
  list.dataset.human = '0';
  modeLabel.textContent = MODE_TEXT.regras;
  send('oi');
});

send('oi');
