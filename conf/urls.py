from django.contrib import admin
from django.urls import path, include, re_path  # re_path ni import qilamiz
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve           # serve ni import qilamiz
from raspisaniya import views as rasp_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('raspisaniya/', include('raspisaniya.urls')),
    path('api/stats/', rasp_views.stats_api, name='stats_api_global'),
]

# DEBUG qiymatidan qat'i nazar (False bo'lsa ham) static fayllarni o'qish uchun:
urlpatterns += [
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'static'}),
]