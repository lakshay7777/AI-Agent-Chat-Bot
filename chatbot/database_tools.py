from typing import List, Dict, Any
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import UserProfile, ChatMessage, PDFDocument, PDFUrl


class DatabaseTools:
    """Tools for querying the database using natural language"""
    
    @staticmethod
    def get_database_schema() -> str:
        """Return database schema information for the LLM"""
        schema = """
        DATABASE SCHEMA:
        
        1. User (Django built-in):
           - id: Primary key
           - username: Unique username
           - email: User email
           - first_name: First name
           - last_name: Last name
           - date_joined: When user registered
           - is_active: Whether user is active
           - last_login: Last login time
        
        2. UserProfile:
           - user: One-to-one with User
           - phone: Phone number
           - bio: User biography
           - created_at: Profile creation time
        
        3. ChatMessage:
           - user: Foreign key to User
           - message: User's message
           - response: AI response
           - timestamp: When message was sent
        
        4. PDFDocument:
           - user: Foreign key to User
           - name: PDF file name
           - file: PDF file path
           - uploaded_at: Upload timestamp
           - is_active: Whether PDF is currently active
        
        5. PDFUrl:
           - user: Foreign key to User
           - name: PDF URL name
           - url: PDF URL
           - uploaded_at: When URL was added
           - is_active: Whether PDF URL is currently active
        """
        return schema
    
    @staticmethod
    def get_user_statistics() -> Dict[str, Any]:
        """Get general user statistics"""
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        users_with_profiles = UserProfile.objects.count()
        
        # Users registered in last 7 days
        week_ago = timezone.now() - timedelta(days=7)
        recent_users = User.objects.filter(date_joined__gte=week_ago).count()
        
        # Users registered in last 30 days
        month_ago = timezone.now() - timedelta(days=30)
        monthly_users = User.objects.filter(date_joined__gte=month_ago).count()
        
        # Users registered yesterday
        yesterday_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        yesterday_end = yesterday_start + timedelta(days=1)
        yesterday_users = User.objects.filter(date_joined__gte=yesterday_start, date_joined__lt=yesterday_end).count()
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'users_with_profiles': users_with_profiles,
            'users_last_week': recent_users,
            'users_last_month': monthly_users,
            'users_yesterday': yesterday_users
        }
    
    @staticmethod
    def get_users_by_date_range(days: int) -> List[Dict[str, Any]]:
        """Get users registered in the last N days"""
        start_date = timezone.now() - timedelta(days=days)
        users = User.objects.filter(date_joined__gte=start_date).values(
            'id', 'username', 'email', 'first_name', 'last_name', 'date_joined'
        )
        return list(users)
    
    @staticmethod
    def get_chat_statistics() -> Dict[str, Any]:
        """Get chat message statistics"""
        total_messages = ChatMessage.objects.count()
        
        # Messages in last 24 hours
        day_ago = timezone.now() - timedelta(days=1)
        daily_messages = ChatMessage.objects.filter(timestamp__gte=day_ago).count()
        
        # Messages in last week
        week_ago = timezone.now() - timedelta(days=7)
        weekly_messages = ChatMessage.objects.filter(timestamp__gte=week_ago).count()
        
        # Most active users (by message count)
        active_users = ChatMessage.objects.values('user__username').annotate(
            message_count=Count('id')
        ).order_by('-message_count')[:5]
        
        return {
            'total_messages': total_messages,
            'messages_last_24h': daily_messages,
            'messages_last_week': weekly_messages,
            'most_active_users': list(active_users)
        }
    
    @staticmethod
    def get_pdf_statistics() -> Dict[str, Any]:
        """Get PDF upload statistics"""
        total_pdf_files = PDFDocument.objects.count()
        total_pdf_urls = PDFUrl.objects.count()
        active_pdf_files = PDFDocument.objects.filter(is_active=True).count()
        active_pdf_urls = PDFUrl.objects.filter(is_active=True).count()
        
        # Recent uploads
        week_ago = timezone.now() - timedelta(days=7)
        recent_pdf_files = PDFDocument.objects.filter(uploaded_at__gte=week_ago).count()
        recent_pdf_urls = PDFUrl.objects.filter(uploaded_at__gte=week_ago).count()
        
        return {
            'total_pdf_files': total_pdf_files,
            'total_pdf_urls': total_pdf_urls,
            'active_pdf_files': active_pdf_files,
            'active_pdf_urls': active_pdf_urls,
            'recent_pdf_files': recent_pdf_files,
            'recent_pdf_urls': recent_pdf_urls
        }
    
    @staticmethod
    def search_users(query: str) -> List[Dict[str, Any]]:
        """Search users by username, email, or name"""
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).values('id', 'username', 'email', 'first_name', 'last_name', 'date_joined')[:10]
        
        return list(users)
    
    @staticmethod
    def get_user_activity(username: str = None, user_id: int = None) -> Dict[str, Any]:
        """Get activity for a specific user"""
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return {'error': 'User not found'}
        elif user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return {'error': 'User not found'}
        else:
            return {'error': 'Username or user_id required'}
        
        # Get user's chat messages count
        message_count = ChatMessage.objects.filter(user=user).count()
        
        # Get user's PDF uploads
        pdf_files = PDFDocument.objects.filter(user=user).count()
        pdf_urls = PDFUrl.objects.filter(user=user).count()
        
        # Last message
        last_message = ChatMessage.objects.filter(user=user).first()
        
        return {
            'user_info': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': f"{user.first_name} {user.last_name}".strip(),
                'date_joined': user.date_joined,
                'last_login': user.last_login,
                'is_active': user.is_active
            },
            'activity': {
                'total_messages': message_count,
                'pdf_files_uploaded': pdf_files,
                'pdf_urls_added': pdf_urls,
                'last_message_time': last_message.timestamp if last_message else None
            }
        }


def query_database(query_type: str, days: int = 7, query: str = "", username: str = "", user_id: int = None) -> str:
    """
    Query the database based on natural language intent
    
    Args:
        query_type: Type of query (user_stats, chat_stats, pdf_stats, user_search, user_activity, users_by_date)
        days: Number of days for date-based queries (default: 7)
        query: Search query for user search (default: "")
        username: Username for user activity query (default: "")
        user_id: User ID for user activity query (default: None)
    """
    print(f"DEBUG: query_database called with query_type='{query_type}', days={days}, query='{query}', username='{username}', user_id={user_id}")
    
    db_tools = DatabaseTools()
    
    try:
        if query_type == "user_stats":
            stats = db_tools.get_user_statistics()
            return f"""User Statistics:
- Total Users: {stats['total_users']}
- Active Users: {stats['active_users']}
- Users with Profiles: {stats['users_with_profiles']}
- New Users (Last Week): {stats['users_last_week']}
- New Users (Last Month): {stats['users_last_month']}
- Users Signed Up Yesterday: {stats['users_yesterday']}"""
        
        elif query_type == "chat_stats":
            stats = db_tools.get_chat_statistics()
            active_users_text = "\n".join([
                f"  - {user['user__username']}: {user['message_count']} messages"
                for user in stats['most_active_users']
            ])
            return f"""Chat Statistics:
- Total Messages: {stats['total_messages']}
- Messages (Last 24h): {stats['messages_last_24h']}
- Messages (Last Week): {stats['messages_last_week']}
- Most Active Users:
{active_users_text}"""
        
        elif query_type == "pdf_stats":
            stats = db_tools.get_pdf_statistics()
            return f"""PDF Statistics:
- Total PDF Files: {stats['total_pdf_files']}
- Total PDF URLs: {stats['total_pdf_urls']}
- Active PDF Files: {stats['active_pdf_files']}
- Active PDF URLs: {stats['active_pdf_urls']}
- Recent PDF Files (Last Week): {stats['recent_pdf_files']}
- Recent PDF URLs (Last Week): {stats['recent_pdf_urls']}"""
        
        elif query_type == "users_by_date":
            users = db_tools.get_users_by_date_range(days)
            if users:
                user_list = "\n".join([
                    f"  - {user['username']} ({user['first_name']} {user['last_name']}) - {user['date_joined'].strftime('%Y-%m-%d %H:%M')}"
                    for user in users
                ])
                return f"Users registered in the last {days} days ({len(users)} users):\n{user_list}"
            else:
                return f"No users registered in the last {days} days."
        
        elif query_type == "user_search":
            users = db_tools.search_users(query)
            if users:
                user_list = "\n".join([
                    f"  - {user['username']} - {user['email']} ({user['first_name']} {user['last_name']})"
                    for user in users
                ])
                return f"Search results for '{query}':\n{user_list}"
            else:
                return f"No users found matching '{query}'"
        
        elif query_type == "user_activity":
            activity = db_tools.get_user_activity(username=username if username else None, user_id=user_id)
            
            if 'error' in activity:
                return f"Error: {activity['error']}"
            
            user_info = activity['user_info']
            user_activity = activity['activity']
            
            return f"""User Activity for {user_info['username']}:
- Full Name: {user_info['full_name']}
- Email: {user_info['email']}
- Joined: {user_info['date_joined'].strftime('%Y-%m-%d')}
- Last Login: {user_info['last_login'].strftime('%Y-%m-%d %H:%M') if user_info['last_login'] else 'Never'}
- Status: {'Active' if user_info['is_active'] else 'Inactive'}
- Total Messages: {user_activity['total_messages']}
- PDF Files Uploaded: {user_activity['pdf_files_uploaded']}
- PDF URLs Added: {user_activity['pdf_urls_added']}
- Last Message: {user_activity['last_message_time'].strftime('%Y-%m-%d %H:%M') if user_activity['last_message_time'] else 'Never'}"""
        
        else:
            return f"Unknown query type: {query_type}. Supported types are: user_stats, chat_stats, pdf_stats, users_by_date, user_search, user_activity"
            
    except Exception as e:
        print(f"DEBUG: Exception in query_database: {str(e)}")
        return f"Database query error: {str(e)}"