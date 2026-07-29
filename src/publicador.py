import os
import sys
import json
import time
import base64
import traceback
import requests
from pathlib import Path

# Credenciais
IG_USER_ID = os.environ["INSTAGRAM_USER_ID"]
IG_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IMGBB_KEY = os.environ["IMGBB_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

DB_DIR = Path("database")
DATA_FILE = DB_DIR / "posts_do_dia.json"

def avisar_telegram(texto):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": texto}, timeout=10)
    except Exception as e:
        print(f"Erro ao avisar Telegram: {e}")

def hospedar_imgbb(caminho_imagem):
    print(f" -> [Etapa 1] Hospedando imagem no ImgBB: {caminho_imagem}")
    with open(caminho_imagem, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    resp = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBB_KEY, "image": img_b64}, timeout=30)
    
    if resp.status_code != 200:
        raise Exception(f"ImgBB HTTP {resp.status_code}: {resp.text[:200]}")
        
    try:
        url = resp.json()["data"]["url"]
        print(f" -> [Etapa 1 OK] URL ImgBB gerada com sucesso!")
        return url
    except Exception:
        raise Exception(f"ImgBB não retornou JSON válido: {resp.text[:200]}")

def publicar_meta(image_url, caption):
    print(" -> [Etapa 2] Iniciando injeção na Graph API da Meta...")
    base_url = "https://graph.instagram.com/v20.0"
    
    # Criar Container (Correção de arquitetura: auth na URL, payload no Body)
    resp = requests.post(
        f"{base_url}/{IG_USER_ID}/media", 
        params={"access_token": IG_TOKEN}, 
        data={"image_url": image_url, "caption": caption},
        timeout=30
    )
    res_json = resp.json()
    container_id = res_json.get("id")
    
    if not container_id:
        raise Exception(f"Meta negou a criação do Container: {res_json}")
    
    print(f" -> [Etapa 2.1] Container {container_id} criado. Aguardando renderização da Meta...")
    
    # Aguardar Processamento
    sucesso_renderizacao = False
    for i in range(12):
        time.sleep(10)
        status_resp = requests.get(f"{base_url}/{container_id}", params={"fields": "status_code", "access_token": IG_TOKEN}, timeout=20).json()
        status = status_resp.get("status_code", "")
        print(f"     ... Status da Meta: {status}")
        
        if status == "FINISHED": 
            sucesso_renderizacao = True
            break
        if status == "ERROR":
            raise Exception(f"Meta destruiu o Container (Erro de Processamento): {status_resp}")
            
    if not sucesso_renderizacao:
        raise Exception("Timeout: A Meta demorou mais de 2 minutos para processar a foto e o sistema abortou.")
        
    # Publicar no Feed (auth na URL, payload no Body)
    print(" -> [Etapa 3] Container pronto. Disparando para o Feed do Instagram...")
    pub_resp = requests.post(
        f"{base_url}/{IG_USER_ID}/media_publish",
        params={"access_token": IG_TOKEN},
        data={"creation_id": container_id},
        timeout=30
    )

    if pub_resp.status_code != 200:
        raise Exception(f"Erro na publicação final (Feed): {pub_resp.text[:200]}")

    print(" -> [Etapa 3 OK] Post publicado no feed!")

def rodar_fila():
    if not DATA_FILE.exists():
        print("Arquivo JSON não encontrado. O coletor rodou?")
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        dados = json.load(f)

    post_da_vez = next((p for p in dados["posts"] if not p["publicado"]), None)
    
    if not post_da_vez:
        print("Todos os posts de hoje já foram publicados!")
        return

    print(f"Iniciando publicação do Post {post_da_vez['id']}...")
    caminho_img = DB_DIR / post_da_vez["imagem"]
    
    if not caminho_img.exists():
        msg_erro = f"Arquivo de imagem '{post_da_vez['imagem']}' não foi encontrado."
        print(f"ERRO FATAL: {msg_erro}")
        avisar_telegram(f"❌ Erro estrutural no Post {post_da_vez['id']}: {msg_erro}")
        sys.exit(1)
    
    try:
        url_publica = hospedar_imgbb(caminho_img)
        publicar_meta(url_publica, post_da_vez["legenda"])
        
        # Trava de Segurança
        post_da_vez["publicado"] = True
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            
        avisar_telegram(f"✅ Instagram Autônomo: Post {post_da_vez['id']}/3 publicado com sucesso!")
        print(f"Post {post_da_vez['id']} finalizado com maestria.")
        
    except Exception as e:
        print("\n" + "="*50)
        print("🚨 ERRO DETECTADO NA EXECUÇÃO 🚨")
        traceback.print_exc()
        print("="*50 + "\n")
        avisar_telegram(f"❌ ERRO ao publicar slide {post_da_vez['id']}:\n{e}")
        sys.exit(1)

if __name__ == "__main__":
    rodar_fila()
