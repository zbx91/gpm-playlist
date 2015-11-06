from django.shortcuts import render
from django.http import HttpResponse

def index(request):
    return HttpResponse("Testing this out.")

# Create your views here.
