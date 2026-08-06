import os
import json
import asyncio
import requests
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

# Pegando chaves do cofre
API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
STRING_SESSION = os.environ["TELEGRAM_STRING_SESSION"]

# ID do chat de onde vem a arte + legenda (obrigatório: sem fallback, para não
# coletar do canal errado por engano)
CHAT_ID_CONTEUDO = int(os.environ["TELEGRAM_CONTENT_CHAT_ID"])

# Avisos vao pelo bot (mesmo mecanismo do publicador.py). Enviar com a sessao
# de usuario faria a mensagem sair de voce para voce mesmo, caindo em
# "Mensagens Salvas" em vez de chegar como notificacao.
BOT_TOKEN_AVISOS = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_AVISOS = os.environ.get("TELEGRAM_CHAT_ID")

DB_DIR = Path("database")
DB_DIR.mkdir(exist_ok=True)
DATA_FILE = DB_DIR / "posts_do_dia.json"
ESTADO_FILE = DB_DIR / "estado_coletor.json"


def avisar_telegram(texto):
    if not (BOT_TOKEN_AVISOS and CHAT_ID_AVISOS):
        print(f"[aviso nao enviado - bot/chat nao configurado] {texto}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN_AVISOS}/sendMessage",
            json={"chat_id": CHAT_ID_AVISOS, "text": texto},
            timeout=10
        )
    except Exception as e:
        print(f"Erro ao avisar Telegram: {e}")


def carregar_ultimo_id():
    if ESTADO_FILE.exists():
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("ultimo_message_id")
    return None


def salvar_ultimo_id(msg_id):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump({"ultimo_message_id": msg_id}, f, ensure_ascii=False, indent=2)


def contar_pendentes():
    if not DATA_FILE.exists():
        return 0
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return sum(1 for p in dados.get("posts", []) if not p.get("publicado"))
    except Exception:
        return 0


async def coletar_posts():
    print(f"Iniciando coleta no Telegram (Chat Alvo: {CHAT_ID_CONTEUDO})...")

    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:

        print("Atualizando a lista de diálogos para o Telethon reconhecer o ID...")
        # A PEÇA QUE FALTAVA: Isso cura a "amnésia" da StringSession
        await client.get_dialogs()

        print("Buscando o chat alvo...")
        chat = await client.get_entity(CHAT_ID_CONTEUDO)

        mensagens = []
        async for msg in client.iter_messages(chat, limit=30):
            mensagens.append(msg)

        mensagens.reverse()

        ultimo_processado = carregar_ultimo_id()
        bootstrap = ultimo_processado is None
        maior_id_visto = max((m.id for m in mensagens), default=(ultimo_processado or 0))

        if bootstrap:
            # Primeira execução com controle de estado: só estabelece o marco,
            # sem reenfileirar conteúdo antigo que possa já ter sido publicado.
            salvar_ultimo_id(maior_id_visto)
            print(f"Marco inicial estabelecido (mensagem {maior_id_visto}). "
                  f"Nenhuma fila gerada neste ciclo — a partir da próxima coleta, "
                  f"apenas conteúdo novo será processado.")
            return

        pares = []
        novas = [m for m in mensagens if m.id > ultimo_processado]
        print(f"Janela lida: {len(mensagens)} mensagens (ultima processada: "
              f"{ultimo_processado}). Novas desde entao: {len(novas)}.")
        for m in novas:
            tipo = type(m.media).__name__ if m.media else "sem midia"
            texto = (m.text or "").strip()
            print(f"  msg {m.id}: midia={tipo}, texto={len(texto)} chars")

        for i, msg in enumerate(mensagens):
            if msg.id <= ultimo_processado:
                continue
            if not msg.media:
                continue
            if not isinstance(msg.media, MessageMediaPhoto):
                print(f"Midia (msg {msg.id}) ignorada: tipo "
                      f"{type(msg.media).__name__}, nao e foto comprimida.")
                avisar_telegram(
                    f"⚠️ Arquivo recebido (msg {msg.id}) foi ignorado: veio como "
                    f"{type(msg.media).__name__} e não como foto. Reenvie a arte "
                    f"como foto (compactada), não como documento/arquivo."
                )
                continue

            legenda = msg.text or ""
            if not legenda:
                for j in range(i + 1, min(i + 4, len(mensagens))):
                    if mensagens[j].text and len(mensagens[j].text) > 30:
                        legenda = mensagens[j].text
                        break

            if "---" in legenda:
                legenda = legenda.split("---", 1)[1].strip()
            if legenda.endswith("---"):
                legenda = legenda[:-3].strip()

            if not legenda:
                print(f"Foto (msg {msg.id}) sem legenda identificável — pulando.")
                avisar_telegram(
                    f"⚠️ Arte encontrada no canal (msg {msg.id}) foi ignorada: "
                    f"não encontrei legenda associada a ela. Adicione a legenda "
                    f"manualmente se quiser publicá-la."
                )
                continue

            pares.append({"msg_obj": msg, "legenda": legenda})

        pares = pares[-3:]

        fila_posts = []
        for index, par in enumerate(pares, 1):
            img_path = str(DB_DIR / f"slide_0{index}.png")
            print(f"Baixando imagem {index}...")
            await client.download_media(par["msg_obj"], file=img_path)

            fila_posts.append({
                "id": index,
                "imagem": f"slide_0{index}.png",
                "legenda": par["legenda"],
                "publicado": False
            })

        if not fila_posts:
            # Nada novo: preserva a fila atual. Sobrescrever aqui descartaria
            # posts ja coletados e ainda nao publicados.
            salvar_ultimo_id(maior_id_visto)
            print("Nenhum conteudo novo. Fila atual preservada.")
            return

        pendentes = contar_pendentes()
        if pendentes:
            avisar_telegram(
                f"⚠️ A fila foi substituída por {len(fila_posts)} post(s) novo(s), "
                f"mas {pendentes} post(s) do lote anterior ainda não tinham sido "
                f"publicados e foram descartados."
            )

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"posts": fila_posts}, f, ensure_ascii=False, indent=2)

        salvar_ultimo_id(maior_id_visto)

        print(f"Coleta finalizada. {len(fila_posts)} posts encontrados.")

if __name__ == "__main__":
    asyncio.run(coletar_posts())
