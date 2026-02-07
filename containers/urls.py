# containers/urls.py
from django.urls import path
from . import views

app_name = "containers"

urlpatterns = [
    path("", views.ContainerListView.as_view(), name="list"),
    path("sarafs/", views.SarafListView.as_view(), name="saraf_list"),
    path("saraf/<uuid:saraf_id>/", views.SarafDetailView.as_view(), name="saraf_detail"),
    path("admin/overview/", views.ContainersAdminOverview.as_view(), name="admin_overview"),
    path("container/<uuid:pk>/", views.ContainerDetailView.as_view(), name="detail"),
]