# ====== CLIENTES (CRUD solo GERENTE/STAFF) ======
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from acarreapp.views import GerenteRequiredMixin
from acarreapp.tenancy import get_current_empresa
from .models import Cliente
from .forms import ClienteForm

class ClienteListView(GerenteRequiredMixin, LoginRequiredMixin, ListView):
    template_name = "empresa/clientes_list.html"
    context_object_name = "clientes"
    paginate_by = 20

    def get_queryset(self):
        emp = get_current_empresa()
        qs = Cliente.objects.filter(empresa=emp)
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(nombre__icontains=q)
        return qs.order_by("nombre")

class ClienteDetailView(GerenteRequiredMixin, LoginRequiredMixin, DetailView):
    template_name = "empresa/clientes_detail.html"
    context_object_name = "cliente"

    def get_queryset(self):
        emp = get_current_empresa()
        return Cliente.objects.filter(empresa=emp)

class ClienteCreateView(GerenteRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = "empresa/clientes_form.html"
    form_class = ClienteForm
    success_url = reverse_lazy("empresa:clientes_list")

    def form_valid(self, form):
        emp = get_current_empresa()
        obj = form.save(commit=False)
        obj.empresa = emp
        obj.save()
        return super().form_valid(form)

class ClienteUpdateView(GerenteRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = "empresa/clientes_form.html"
    form_class = ClienteForm
    success_url = reverse_lazy("empresa:clientes_list")

    def get_queryset(self):
        emp = get_current_empresa()
        return Cliente.objects.filter(empresa=emp)

class ClienteDeleteView(GerenteRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = "empresa/clientes_confirm_delete.html"
    success_url = reverse_lazy("empresa:clientes_list")

    def get_queryset(self):
        emp = get_current_empresa()
        return Cliente.objects.filter(empresa=emp)
