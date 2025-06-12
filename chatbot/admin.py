from django.contrib import admin

# Register your models here.
from .models import User,PDFDocument,PDFUrl,UserProfile,ChatMessage

admin.site.register(PDFDocument)
admin.site.register(PDFUrl)
admin.site.register(UserProfile)
admin.site.register(ChatMessage)