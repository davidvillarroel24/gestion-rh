from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def visor(request):
    return render(request, "visor/visor.html")
