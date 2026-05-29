
import os
import logging
import requests
import json
from fpdf import FPDF
from docx import Document
from PyPDF2 import PdfReader

from telegram import Update, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


# Load environment variables (for local testing, Koyeb handles this)
from dotenv import load_dotenv
load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
BOT_NAME = "Darrvis"

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
POLLINATIONS_API_URL = "https://image.pollinations.ai/prompt/"

WEBHOOK_URL = os.getenv('WEBHOOK_URL') # This will be set by Koyeb
PORT = int(os.getenv('PORT', 8000))

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for conversation context and message count
user_conversations = {}
user_message_counts = {}
MAX_FREE_MESSAGES = 10

# --- Utility Functions ---

async def send_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_chat_action(ChatAction.TYPING)

def get_gemini_response(prompt, chat_history=None):
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": []
    }

    if chat_history:
        for message in chat_history:
            payload["contents"].append({"role": message["role"], "parts": [{"text": message["text"]}]})

    payload["contents"].append({"role": "user", "parts": [{"text": prompt}]})

    params = {"key": GEMINI_API_KEY}
    response = requests.post(GEMINI_API_URL, headers=headers, json=payload, params=params)
    response.raise_for_status()
    return response.json()['candidates'][0]['content']['parts'][0]['text']

# --- Telegram Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    user_id = update.effective_user.id
    user_conversations[user_id] = [] # Initialize conversation history
    user_message_counts[user_id] = 0 # Initialize message count
    welcome_message = (
        f"Salut ! Je suis {BOT_NAME}, votre assistant IA polyvalent et sympathique.\n\n"
        "Je peux répondre à vos questions, générer des images, créer des documents PDF et Word, "
        "lire des fichiers, écrire du code, traduire des langues, et bien plus encore !\n\n"
        "Tapez /aide pour voir la liste de mes fonctionnalités.\n"
        "N'hésitez pas à commencer à discuter avec moi !"
    )
    await update.message.reply_text(welcome_message)

async def aide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    help_message = (
        "Voici ce que je peux faire :\n\n"
        "1. **Chat IA (Gemini)** : Réponds à toutes vos questions et garde le contexte de la conversation.\n"
        "2. **Génération d'images** : Utilisez `/image [description]` pour générer une image (ex: `/image un chat volant`).\n"
        "3. **Création de PDF** : Utilisez `/pdf [sujet]` pour créer un document PDF (ex: `/pdf un rapport sur l'IA`).\n"
        "4. **Création de Word** : Utilisez `/word [sujet]` pour créer un document Word (ex: `/word une lettre de motivation`).\n"
        "5. **Lecture de fichiers** : Envoyez-moi un fichier PDF ou Word, et je pourrai en extraire le texte et répondre à vos questions.\n"
        "6. **Code** : Je peux écrire, corriger ou expliquer du code.\n"
        "7. **Langues** : Je peux traduire du texte dans toutes les langues.\n"
        "8. **Monétisation** : Vous avez 10 messages gratuits par jour. Après cela, je vous demanderai de recharger.\n\n"
        "**Commandes disponibles :**\n"
        "/start - Message de bienvenue\n"
        "/aide - Cette liste de fonctionnalités\n"
        "/image [description] - Générer une image\n"
        "/pdf [sujet] - Créer un PDF\n"
        "/word [sujet] - Créer un Word\n"
        "/reset - Réinitialiser la conversation et le compteur de messages\n"
    )
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    user_id = update.effective_user.id
    user_conversations[user_id] = []
    user_message_counts[user_id] = 0
    await update.message.reply_text("Votre conversation et votre compteur de messages ont été réinitialisés.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in user_message_counts:
        user_message_counts[user_id] = 0
    if user_id not in user_conversations:
        user_conversations[user_id] = []

    if user_message_counts[user_id] >= MAX_FREE_MESSAGES:
        await update.message.reply_text(
            "Vous avez atteint la limite de 10 messages gratuits par jour. "
            "Veuillez recharger votre compte pour continuer à utiliser mes services. "
            "(La fonctionnalité de paiement sera implémentée plus tard.)"
        )
        return

    user_message_counts[user_id] += 1

    # Add user message to conversation history
    user_conversations[user_id].append({"role": "user", "text": text})

    try:
        gemini_response = get_gemini_response(text, user_conversations[user_id])
        # Add bot response to conversation history
        user_conversations[user_id].append({"role": "model", "text": gemini_response})
        await update.message.reply_text(gemini_response)
    except Exception as e:
        logger.error(f"Error getting Gemini response: {e}")
        await update.message.reply_text("Désolé, une erreur est survenue lors de la communication avec l'IA.")

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    user_id = update.effective_user.id

    if user_id not in user_message_counts:
        user_message_counts[user_id] = 0

    if user_message_counts[user_id] >= MAX_FREE_MESSAGES:
        await update.message.reply_text(
            "Vous avez atteint la limite de 10 messages gratuits par jour. "
            "Veuillez recharger votre compte pour continuer à utiliser mes services. "
            "(La fonctionnalité de paiement sera implémentée plus tard.)"
        )
        return

    user_message_counts[user_id] += 1

    if not context.args:
        await update.message.reply_text("Veuillez fournir une description pour l'image. Exemple: `/image un chat volant`")
        return

    description = " ".join(context.args)
    image_url = f"{POLLINATIONS_API_URL}{description}"
    await update.message.reply_photo(photo=image_url, caption=f"Voici votre image pour '{description}'")

async def create_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    user_id = update.effective_user.id

    if user_id not in user_message_counts:
        user_message_counts[user_id] = 0

    if user_message_counts[user_id] >= MAX_FREE_MESSAGES:
        await update.message.reply_text(
            "Vous avez atteint la limite de 10 messages gratuits par jour. "
            "Veuillez recharger votre compte pour continuer à utiliser mes services. "
            "(La fonctionnalité de paiement sera implémentée plus tard.)"
        )
        return

    user_message_counts[user_id] += 1

    if not context.args:
        await update.message.reply_text("Veuillez fournir un sujet pour le PDF. Exemple: `/pdf un rapport sur l'IA`")
        return

    subject = " ".join(context.args)
    file_name = f"rapport_{subject.replace(' ', '_')}.pdf"

    try:
        # Generate content using Gemini
        gemini_prompt = f"Génère un contenu détaillé pour un document PDF sur le sujet suivant : {subject}. Le contenu doit être bien structuré avec des titres et des paragraphes. Utilise le français."
        content = get_gemini_response(gemini_prompt)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, content.encode('latin-1', 'replace').decode('latin-1')) # Ensure proper encoding
        pdf.output(file_name)

        with open(file_name, 'rb') as f:
            await update.message.reply_document(document=f, caption=f"Voici votre document PDF sur '{subject}'.")
        os.remove(file_name)
    except Exception as e:
        logger.error(f"Error creating PDF: {e}")
        await update.message.reply_text("Désolé, une erreur est survenue lors de la création du document PDF.")

async def create_word_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    user_id = update.effective_user.id

    if user_id not in user_message_counts:
        user_message_counts[user_id] = 0

    if user_message_counts[user_id] >= MAX_FREE_MESSAGES:
        await update.message.reply_text(
            "Vous avez atteint la limite de 10 messages gratuits par jour. "
            "Veuillez recharger votre compte pour continuer à utiliser mes services. "
            "(La fonctionnalité de paiement sera implémentée plus tard.)"
        )
        return

    user_message_counts[user_id] += 1

    if not context.args:
        await update.message.reply_text("Veuillez fournir un sujet pour le document Word. Exemple: `/word une lettre de motivation`")
        return

    subject = " ".join(context.args)
    file_name = f"document_{subject.replace(' ', '_')}.docx"

    try:
        # Generate content using Gemini
        gemini_prompt = f"Génère un contenu détaillé pour un document Word sur le sujet suivant : {subject}. Le contenu doit être bien structuré avec des titres et des paragraphes. Utilise le français."
        content = get_gemini_response(gemini_prompt)

        document = Document()
        document.add_heading(subject, level=1)
        for paragraph in content.split('\n\n'): # Split by double newline for paragraphs
            document.add_paragraph(paragraph)
        document.save(file_name)

        with open(file_name, 'rb') as f:
            await update.message.reply_document(document=f, caption=f"Voici votre document Word sur '{subject}'.")
        os.remove(file_name)
    except Exception as e:
        logger.error(f"Error creating Word document: {e}")
        await update.message.reply_text("Désolé, une erreur est survenue lors de la création du document Word.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_typing_action(update, context)
    user_id = update.effective_user.id

    if user_id not in user_message_counts:
        user_message_counts[user_id] = 0

    if user_message_counts[user_id] >= MAX_FREE_MESSAGES:
        await update.message.reply_text(
            "Vous avez atteint la limite de 10 messages gratuits par jour. "
            "Veuillez recharger votre compte pour continuer à utiliser mes services. "
            "(La fonctionnalité de paiement sera implémentée plus tard.)"
        )
        return

    user_message_counts[user_id] += 1

    document = update.message.document
    file_name = document.file_name

    if file_name.endswith('.pdf'):
        file_path = await document.get_file()
        downloaded_file = await file_path.download_to_drive()
        
        try:
            reader = PdfReader(downloaded_file)
            text_content = ""
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
            
            # Store the extracted text for later querying (simple in-memory for now)
            user_conversations[user_id].append({"role": "system", "text": f"Contenu du PDF '{file_name}':\n{text_content[:1000]}..."}) # Store first 1000 chars
            await update.message.reply_text(f"J'ai lu le document PDF '{file_name}'. Vous pouvez maintenant me poser des questions à ce sujet.")
        except Exception as e:
            logger.error(f"Error reading PDF: {e}")
            await update.message.reply_text("Désolé, une erreur est survenue lors de la lecture du document PDF.")
        finally:
            os.remove(downloaded_file)

    elif file_name.endswith('.docx'):
        file_path = await document.get_file()
        downloaded_file = await file_path.download_to_drive()

        try:
            doc = Document(downloaded_file)
            text_content = "\n".join([paragraph.text for paragraph in doc.paragraphs])

            # Store the extracted text for later querying
            user_conversations[user_id].append({"role": "system", "text": f"Contenu du document Word '{file_name}':\n{text_content[:1000]}..."}) # Store first 1000 chars
            await update.message.reply_text(f"J'ai lu le document Word '{file_name}'. Vous pouvez maintenant me poser des questions à ce sujet.")
        except Exception as e:
            logger.error(f"Error reading Word document: {e}")
            await update.message.reply_text("Désolé, une erreur est survenue lors de la lecture du document Word.")
        finally:
            os.remove(downloaded_file)

    else:
        await update.message.reply_text("Désolé, je ne peux lire que les fichiers PDF et Word pour le moment.")

# --- Main Application Setup ---

async def post_init(application: Application):
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=f'{WEBHOOK_URL}/{TELEGRAM_TOKEN}')
        logger.info(f"Webhook set to {WEBHOOK_URL}/{TELEGRAM_TOKEN}")
    else:
        logger.warning("WEBHOOK_URL not set, webhook will not be configured.")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("aide", aide))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("image", generate_image_command))
    application.add_handler(CommandHandler("pdf", create_pdf_command))
    application.add_handler(CommandHandler("word", create_word_command))

    # Message Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.PDF | filters.Document.DOCX, handle_document))

    # Start the bot in webhook mode
    if WEBHOOK_URL:
        logger.info(f"Starting webhook on port {PORT} with URL {WEBHOOK_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
        )
    else:
        logger.info("WEBHOOK_URL not set, falling back to polling mode.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
