from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required


def login_view(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            group = user.groups.first()
            if group and group.name == "admin":
                return redirect("admin_dashboard")
            elif group and group.name == "vendedor":
                return redirect("vendedor_dashboard")
        else:
            return render(
                request, "core/login.html", {"error": "Credenciales incorrectas"}
            )

    return render(request, "core/login.html")


@login_required
def redirect_dashboard(request):
    group = request.user.groups.first()
    if group and group.name == "admin":
        return redirect("admin_dashboard")
    elif group and group.name == "vendedor":
        return redirect("vendedor_dashboard")
    else:
        return redirect("login")
