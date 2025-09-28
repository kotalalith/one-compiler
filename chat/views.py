import os
import io
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .forms import UploadPDFForm

# External libs
import google.generativeai as genai
from pdfminer.high_level import extract_text  # ✅ correct PDF parser

# Load API key from env
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Warning: GOOGLE_API_KEY not set. Set environment variable GOOGLE_API_KEY to use Gemini.")

genai.configure(api_key=GOOGLE_API_KEY)

class GeminiChat:
    def __init__(self, model_name: str = "gemini-2.0-flash"):
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)
        self.chat = self.model.start_chat(history=[])
        self.pdf_content = ""

    def get_response(self, user_input: str) -> str:
        try:
            if self.pdf_content:
                context = self._get_relevant_context(user_input, self.pdf_content)
                prompt = f"""You are a helpful AI assistant that answers questions about the provided PDF content.

PDF Content:
{context}

Question: {user_input}

Please provide a detailed and accurate response based on the PDF content. If the answer cannot be found in the PDF, please state that clearly."""
            else:
                prompt = f"""You are a helpful AI assistant.

Question: {user_input}

Please provide a helpful response. Note: No PDF has been uploaded yet."""
            response = self.chat.send_message(prompt)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

    def _get_relevant_context(self, question: str, full_text: str, max_length: int = 4000) -> str:
        return full_text[:max_length] + ("..." if len(full_text) > max_length else "")

    def clear_history(self):
        self.chat = self.model.start_chat(history=[])
        self.pdf_content = ""

    def extract_text_from_pdf_bytes(self, file_bytes: bytes) -> dict:
        try:
            with io.BytesIO(file_bytes) as pdf_stream:
                text = extract_text(pdf_stream)
            if not text.strip():
                return {
                    "status": "error",
                    "message": "No text could be extracted from the PDF. It might be scanned or image-based."
                }
            self.pdf_content = text[:1000000]  # store up to 1M chars
            return {
                "status": "success",
                "message": "PDF uploaded successfully.",
                "content_preview": text[:1000] + ("..." if len(text) > 1000 else "")
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to process PDF: {str(e)}"}

# Single global chatbot instance
chatbot = GeminiChat()

def index(request):
    return render(request, "chat/index.html", {"has_pdf": bool(chatbot.pdf_content)})

@csrf_exempt
@require_http_methods(["POST"])
def chat_endpoint(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
        message = body.get("message", "").strip()
        if not message:
            return JsonResponse({"status": "error", "message": "Message cannot be empty"}, status=400)
        response = chatbot.get_response(message)
        return JsonResponse({
            "status": "success",
            "response": response,
            "has_pdf_context": bool(chatbot.pdf_content)
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def upload_pdf(request):
    form = UploadPDFForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"status": "error", "message": "No file provided or file invalid"}, status=400)

    file = request.FILES["file"]
    if not file.name.lower().endswith(".pdf"):
        return JsonResponse({"status": "error", "message": "File must be a PDF"}, status=400)

    max_size = 10 * 1024 * 1024  # 10MB
    if file.size == 0:
        return JsonResponse({"status": "error", "message": "Uploaded file is empty"}, status=400)
    if file.size > max_size:
        return JsonResponse({"status": "error", "message": f"File size exceeds {max_size//(1024*1024)}MB"}, status=400)

    try:
        content = file.read()
        result = chatbot.extract_text_from_pdf_bytes(content)
        if result.get("status") == "success":
            chatbot.clear_history()
            chatbot.pdf_content = result.get("content_preview", "").replace("...", "")
            result["text_length"] = len(chatbot.pdf_content)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"Unexpected error: {str(e)}"}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def clear_chat(request):
    chatbot.clear_history()
    return JsonResponse({"status": "chat history cleared"})

@csrf_exempt
@require_http_methods(["POST"])
def detach_pdf(request):
    chatbot.clear_history()
    return JsonResponse({"status": "PDF detached successfully"})

def health_check(request):
    try:
        _ = chatbot.get_response("Test message")
        return JsonResponse({
            "status": "healthy",
            "model": chatbot.model_name,
            "has_pdf_context": bool(chatbot.pdf_content)
        })
    except Exception as e:
        return JsonResponse({"status": "unhealthy", "error": str(e)}, status=500)
