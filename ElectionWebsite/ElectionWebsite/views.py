from django.shortcuts import render

def home(request):
    '''
        View for the home page - currently returns placeholder
    '''

    context = {
        'content': "This is the home page",
    }

    return render(request, "base.html", context)
