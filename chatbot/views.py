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
# from .database_tools import DatabaseTools, create_database_query_function
from agno.embedder.google import GeminiEmbedder
from .database_tools import DatabaseTools, query_database

import re

storage = SqliteStorage(table_name = "chat_history_last_30", db_file = "temp/data.db")


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

@login_required
def check_pdf_status(request):
    """Check if user has an active PDF document"""
    active_pdf = PDFDocument.objects.filter(user=request.user, is_active=True).first()
    active_pdf_url = PDFUrl.objects.filter(user=request.user, is_active=True).first()
    
    if active_pdf:
        return JsonResponse({
            'has_pdf': True,
            'pdf_name': active_pdf.name,
            'pdf_type': 'file'
        })
    elif active_pdf_url:
        return JsonResponse({
            'has_pdf': True,
            'pdf_name': active_pdf_url.name,
            'pdf_type': 'url'
        })
    else:
        return JsonResponse({
            'has_pdf': False,
            'pdf_name': None,
            'pdf_type': None
        })

def detect_database_query(query: str) -> dict:
    """
    Detect if the query is asking for database information and determine the query type
    """
    query_lower = query.lower()
    
    # Database query patterns - matching the actual query_database function parameters
    patterns = {
        'user_stats': [
            r'how many users?', r'total users?', r'user count', r'number of users',
            r'user statistics', r'user stats', r'how many people', r'user overview',
            r'active users', r'recent signups', r'new users'
        ],
        'chat_stats': [
            r'chat statistics', r'message stats', r'chat stats', r'how many messages',
            r'message count', r'chat activity', r'conversation stats', r'most active users'
        ],
        'pdf_stats': [
            r'pdf statistics', r'pdf stats', r'how many pdfs', r'pdf count',
            r'document stats', r'upload stats', r'pdf uploads'
        ],
        'users_by_date': [
            r'users? (?:registered|signed up|joined) (?:in )?(?:the )?last (\d+) days?',
            r'new users (?:in )?(?:the )?last (\d+) days?',
            r'recent users (\d+) days?',
            r'users? (?:from|in) (?:the )?last (\d+) days?'
        ],
        'user_search': [
            r'find user (.+)', r'search user (.+)', r'look for user (.+)',
            r'user named (.+)', r'user with (.+)'
        ],
        'user_activity': [
            r'activity (?:of|for) user (.+)', r'user (.+) activity',
            r'what has user (.+) done', r'(.+) user stats'
        ]
    }
    
    for query_type, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, query_lower)
            if match:
                result = {'type': query_type, 'match': True}
                
                # Extract parameters based on query type
                if query_type == 'users_by_date' and match.groups():
                    result['days'] = int(match.group(1))
                elif query_type in ['user_search', 'user_activity'] and match.groups():
                    result['query'] = match.group(1).strip()
                
                return result
    
    return {'type': None, 'match': False}


@csrf_exempt
@login_required
def chatbot_api(request):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'error': 'Invalid method'}, status=405)

    try:
        data = json.loads(request.body)
        user_query = data.get('query', '').strip()
        mode = data.get('mode', '').strip()

        if not user_query:
            return JsonResponse({'status': False, 'error': 'No query provided'}, status=400)
        
        if not mode:
            return JsonResponse({'status': False, 'error': 'No mode selected'}, status=400)

        # Handle different modes
        if mode == 'database':
            # Database mode - use database tools
            user_agent = get_database_agent(request.user)
        elif mode == 'general':
            # General mode - use web search, reasoning, finance tools
            user_agent = get_general_agent(request.user)
        elif mode == 'pdf':
            # PDF mode - check if user has active PDF
            active_pdf = PDFDocument.objects.filter(user=request.user, is_active=True).first()
            active_pdf_url = PDFUrl.objects.filter(user=request.user, is_active=True).first()
            
            if not active_pdf and not active_pdf_url:
                return JsonResponse({
                    'status': False, 
                    'error': 'Please upload a PDF file or provide a PDF URL first'
                }, status=400)
            
            user_agent = get_pdf_agent(request.user)
        else:
            return JsonResponse({'status': False, 'error': 'Invalid mode'}, status=400)

        # Get response from agent
        response = user_agent.run(user_query)
        
        if hasattr(response, 'content'):
            ai_response = response.content
        else:
            ai_response = str(response)

        # Save chat message with mode
        ChatMessage.objects.create(
            user=request.user,
            message=f"[{mode.upper()}] {user_query}",
            response=ai_response
        )

        return JsonResponse({'status': True, 'response': ai_response})
        
    except Exception as e:
        print(f"Error in chatbot_api: {str(e)}")
        return JsonResponse({'status': False, 'error': 'Something went wrong'}, status=500)


def get_database_agent(user):
    """Create agent specifically for database queries"""
    API_key = "AIzaSyCWjyirQA7oIhHKrM3sF5ndv0HY2T62Vvw"
    
    # Create database query function
    # database_query_func = create_database_query_function()
    database_query_func = query_database

    
    # Get database schema for context
    db_schema = DatabaseTools.get_database_schema()
    
    agent = Agent(
        model=Gemini(id="gemini-2.0-flash-exp", api_key=API_key),
        storage=storage,
        add_history_to_messages=True,
        num_history_runs=5,
        # tools=[database_query_func],
        # tools=[database_query_func],
        tools=[query_database],

        instructions=[
            "You are a database assistant for this application.",
            "Your primary function is to answer questions about the application's database.",
            "Use the query_database function to get information about users, messages, and PDF uploads.",
            "Be precise and provide statistical information when requested.",
            "Always format your responses clearly with proper headings and bullet points.",
            "",
            "IMPORTANT: When using the query_database function, use these exact query_type values:",
            "- 'user_stats' for user statistics (total users, active users, recent signups)",
            "- 'chat_stats' for chat/message statistics",
            "- 'pdf_stats' for PDF upload statistics", 
            "- 'user_search' for searching specific users (provide the 'query' parameter)",
            "- 'user_activity' for getting user activity (provide 'username' parameter)",
            "- 'users_by_date' for users by date range (provide 'days' parameter)",
            "",
            "EXAMPLES:",
            "- For 'How many users are registered?': use query_type='user_stats'",
            "- For 'Find user john': use query_type='user_search', query='john'",
            "- For 'Users in last 30 days': use query_type='users_by_date', days=30",
            "- For 'Chat statistics': use query_type='chat_stats'",
            "- For 'PDF statistics': use query_type='pdf_stats'",
            "",
            db_schema
        ],
        markdown=True,
    )
    
    return agent


def get_general_agent(user):
    """Create agent for general questions with web search, reasoning, and finance tools"""
    API_key = "AIzaSyCWjyirQA7oIhHKrM3sF5ndv0HY2T62Vvw"
    
    agent = Agent(
        model=Gemini(id="gemini-2.0-flash-exp", api_key=API_key),
        storage=storage,
        add_history_to_messages=True,
        num_history_runs=5,
        tools=[DuckDuckGoTools(), ReasoningTools(), YFinanceTools()],
        instructions=[
            "You are a general-purpose AI assistant with access to web search, reasoning, and financial data",
            "Use DuckDuckGo for web searches when you need current information",
            "Use ReasoningTools for complex logical problems and step-by-step analysis", 
            "Use YFinance for stock prices, financial data, and market information",
            "Provide comprehensive, well-researched answers",
            "Always cite your sources when using web search results",
            "For financial queries, provide current data and relevant analysis",
            "Be helpful, accurate, and educational in your responses"
        ],
        markdown=True,
    )
    
    return agent


def get_pdf_agent(user):
    """Create agent for PDF-related questions"""
    API_key = "AIzaSyCWjyirQA7oIhHKrM3sF5ndv0HY2T62Vvw"
    
    # Get active PDF
    active_pdf = PDFDocument.objects.filter(user=user, is_active=True).first()
    active_pdf_url = PDFUrl.objects.filter(user=user, is_active=True).first()
    
    COLLECTION_NAME = f"pdf-user-{user.id}"
    # vector_db = Qdrant(collection=COLLECTION_NAME, url="http://localhost:8000")
    # from agno.embedder.google import GeminiEmbedder
    vector_db = Qdrant(collection=COLLECTION_NAME, url="http://localhost:8000")
    # vector_db = Qdrant(
    #     collection=COLLECTION_NAME, 
    #     url="http://localhost:8000",
    #     embedder=GeminiEmbedder(api_key=API_key)
    # )
    # vector_db = Qdrant(
    # collection=COLLECTION_NAME, 
    # url=":memory:",
    # embedder=GeminiEmbedder(api_key=API_key)
    # )
    # vector_db = Qdrant(
    # collection=COLLECTION_NAME, 
    # url="http://localhost:6333",
    # embedder=GeminiEmbedder(api_key=API_key)
    # )
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
        num_history_runs=5,
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
    
    return agent