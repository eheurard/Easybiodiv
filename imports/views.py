from django.http import HttpResponse

def index(request):
    return HttpResponse('imports index — WIP')

def download_template(request):
    return HttpResponse('download_template — WIP')

def upload(request):
    return HttpResponse('upload — WIP')

def preview(request):
    return HttpResponse('preview — WIP')

def confirm(request):
    return HttpResponse('confirm — WIP')
