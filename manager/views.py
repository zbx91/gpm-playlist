from google.appengine.api import users
from django.http import HttpResponse
from django.shortcuts import render

# Create your views here.

def index(request):
    context = {}
    return render(request, 'manager/index.html', context)


def user(request):
    user = users.get_current_user()
    resp = '''
    <html>
        <head>User Info</head>
        <body>
            <pre>
                users.get_current_user() = {user}
                    - auth_domain = {auth_domain!r}
                    - email = {email!r}
                    - nickname = {nickname!r}
                    - user_id = {user_id!r}
                    - federated_identity = {federated_identity!r}
                    - federated_provider = {federated_provider!r}
                    - dir(user) = {items!r}
            </pre>
        </body>
    </html>
    '''.format(user=user, auth_domain=user.auth_domain(), email=user.email(), nickname=user.nickname(), user_id=user.user_id(), federated_identity=user.federated_identity(), federated_provider=user.federated_provider(), items=dir(user))
    
    return HttpResponse(resp)