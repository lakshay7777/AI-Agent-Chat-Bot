import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from agno.agent import Agent
from agno.models.google import Gemini
from agno.team.team import Team
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.reasoning import ReasoningTools
from agno.tools.yfinance import YFinanceTools
from .models import UserProfile, ChatMessage

from agno.knowledge.pdf_url import PDFUrlKnowledgeBase, PDFUrlReader
from agno.vectordb.qdrant import Qdrant
import asyncio
from agno.storage.sqlite import SqliteStorage
from django.core.files.storage import default_storage
from django.conf import settings
import os
from .models import UserProfile, ChatMessage, PDFDocument
from .models import UserProfile, ChatMessage, PDFDocument, PDFUrl

storage = SqliteStorage(table_name = "chat_history_last_30", db_file = "temp/data.db")


# API_key = "AIzaSyCWjyirQA7oIhHKrM3sF5ndv0HY2T62Vvw"

# COLLECTION_NAME = "pdf-url-reader"

# vector_db = Qdrant(collection=COLLECTION_NAME, url="http://localhost:8000")

# knowledge_base = PDFUrlKnowledgeBase(
#     urls=["https://www.drishtiias.com/images/pdf/NCERT-Class-10-Science.pdf"],
#     vector_db=vector_db,
#     reader=PDFUrlReader(chunk=True),
# )

# pdf_agent = Agent(
#     model=Gemini(id="gemini-2.0-flash-exp", api_key=API_key),
#     knowledge=knowledge_base,
#     search_knowledge=True,
#     storage = storage,
#     add_history_to_messages = True,
#     num_history_runs = 10,
#     instructions=[
#         "You are a helpful AI assistant with access to NCERT Class 10 Science textbook",
#         "Answer questions based on the knowledge from the PDF and your general knowledge",
#         "If the question is related to Class 10 Science topics, prioritize information from the textbook",
#         "Be clear, educational, and provide detailed explanations",
#         "If you can't find relevant information in the textbook, use your general knowledge to help",
#         "and also give me source that you use to replay the questions"
#     ],
#     markdown=True,
# )


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'login.html')

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return render(request, 'signup.html')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return render(request, 'signup.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return render(request, 'signup.html')
        
        try:
            user = User.objects.create_user(username=username, email=email, password=password)
            UserProfile.objects.create(user=user)
            messages.success(request, 'Account created successfully! Please login.')
            return redirect('login')
        except Exception as e:
            messages.error(request, 'Error creating account')
    
    return render(request, 'signup.html')

@login_required
def profile_view(request):
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        # Update user info
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.email = request.POST.get('email', '')
        request.user.save()
        
        # Update profile info
        profile.phone = request.POST.get('phone', '')
        profile.bio = request.POST.get('bio', '')
        profile.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    
    return render(request, 'profile.html', {'profile': profile})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def home(request):
    return render(request, 'home.html')
@login_required
def upload_pdf(request):
    if request.method == 'POST':
        if 'pdf_file' not in request.FILES:
            messages.error(request, 'No file selected')
            return redirect('home')
        
        pdf_file = request.FILES['pdf_file']
        
        if not pdf_file.name.endswith('.pdf'):
            messages.error(request, 'Please upload a PDF file only')
            return redirect('home')
        
      
                # Deactivate all previous PDFs and URLs for this user
        PDFDocument.objects.filter(user=request.user).update(is_active=False)
        PDFUrl.objects.filter(user=request.user).update(is_active=False)
        
        # Save new PDF
        pdf_doc = PDFDocument.objects.create(
            user=request.user,
            name=pdf_file.name,
            file=pdf_file,
            is_active=True
        )
        
        messages.success(request, f'PDF "{pdf_file.name}" uploaded successfully!')
        return redirect('home')
    
    return redirect('home')

@login_required
def add_pdf_url(request):
    if request.method == 'POST':
        pdf_url = request.POST.get('pdf_url', '').strip()
        pdf_name = request.POST.get('pdf_name', '').strip()
        
        if not pdf_url:
            messages.error(request, 'Please provide a PDF URL')
            return redirect('home')
        
        if not pdf_name:
            pdf_name = pdf_url.split('/')[-1] or 'Online PDF'
        
        # Deactivate all previous PDFs and URLs for this user
        PDFDocument.objects.filter(user=request.user).update(is_active=False)
        PDFUrl.objects.filter(user=request.user).update(is_active=False)
        
        # Save new PDF URL
        pdf_url_doc = PDFUrl.objects.create(
            user=request.user,
            name=pdf_name,
            url=pdf_url,
            is_active=True
        )
        
        messages.success(request, f'PDF URL "{pdf_name}" added successfully!')
        return redirect('home')
    
    return redirect('home')

def get_user_agent(user):
    """Create agent with user's active PDF/URL or fallback to general model"""
    API_key = "AIzaSyCWjyirQA7oIhHKrM3sF5ndv0HY2T62Vvw"
    
    # Check if user has an active PDF file
    active_pdf = PDFDocument.objects.filter(user=user, is_active=True).first()
    active_pdf_url = PDFUrl.objects.filter(user=user, is_active=True).first()
    
    if active_pdf or active_pdf_url:
        COLLECTION_NAME = f"pdf-user-{user.id}"
        vector_db = Qdrant(collection=COLLECTION_NAME, url="http://localhost:8000")
        
        if active_pdf:
            # Use uploaded PDF file
            pdf_path = active_pdf.file.path
            source_name = active_pdf.name
            urls = [pdf_path]
        else:
            # Use PDF URL
            pdf_url = active_pdf_url.url
            source_name = active_pdf_url.name
            urls = [pdf_url]
        
        knowledge_base = PDFUrlKnowledgeBase(
            urls=urls,
            vector_db=vector_db,
            reader=PDFUrlReader(chunk=True),
        )
        
        agent = Agent(
            model=Gemini(id="gemini-2.0-flash-exp", api_key=API_key),
            knowledge=knowledge_base,
            search_knowledge=True,
            storage=storage,
            add_history_to_messages=True,
            num_history_runs=10,
            instructions=[
                f"You are a helpful AI assistant with access to the PDF: {source_name}",
                "Answer questions based on the knowledge from the PDF and your general knowledge",
                "If the question is related to topics in the PDF, prioritize information from the document",
                "Be clear, educational, and provide detailed explanations",
                "If you can't find relevant information in the PDF, use your general knowledge to help",
                "Always mention the source of your information (PDF document or general knowledge)"
            ],
            markdown=True,
        )
    else:
        # Fallback to general Gemini model without PDF knowledge
        agent = Agent(
            model=Gemini(id="gemini-2.0-flash-exp", api_key=API_key),
            storage=storage,
            add_history_to_messages=True,
            num_history_runs=10,
            instructions=[
                "You are a helpful AI assistant",
                "Answer questions using your general knowledge",
                "Be clear, educational, and provide detailed explanations",
                "If you need specific document context, ask the user to upload a relevant PDF or provide a PDF URL"
            ],
            markdown=True,
        )
    
    return agent

@csrf_exempt
@login_required
def chatbot_api(request):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'error': 'Invalid method'}, status=405)

    try:
        data = json.loads(request.body)
        user_query = data.get('query', '').strip()

        if not user_query:
            return JsonResponse({'status': False, 'error': 'No query provided'}, status=400)

        # Get user-specific agent
        user_agent = get_user_agent(request.user)
        
        # Get AI response
        response = user_agent.run(user_query)
        
        if hasattr(response, 'content'):
            ai_response = response.content
        else:
            ai_response = str(response)

        # Save chat message
        ChatMessage.objects.create(
            user=request.user,
            message=user_query,
            response=ai_response
        )

        return JsonResponse({'status': True, 'response': ai_response})
        
    except Exception as e:
        print(f"Error in chatbot_api: {str(e)}")
        return JsonResponse({'status': False, 'error': 'Something went wrong'}, status=500)