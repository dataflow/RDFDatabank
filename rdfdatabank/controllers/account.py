#-*- coding: utf-8 -*-
"""
Copyright (c) 2012 University of Oxford

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, --INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from pylons import url
from pylons import request, response, session, tmpl_context as c, url, app_globals as ag
from rdfdatabank.lib.base import BaseController, render
from pylons.controllers.util import abort, redirect
from paste.request import get_cookies
from webob.exc import HTTPUnauthorized
from urllib import unquote

class AccountController(BaseController):
    def login(self):
        #c.ident = None
        #c.ident = request.environ.get('repoze.who.identity')
        #script_name = request.environ.get('SCRIPT_NAME') or '/'
        #referer = request.environ.get('HTTP_REFERER', script_name)

        #if not c.ident:
        #    abort(401, "Not Authorised")
        c.login_counter = request.environ.get('repoze.who.logins', 1)
        if c.login_counter > 0:
            session['login_flash'] = """Wrong credentials. Have you been registered?"""
            session.save()
        c.came_from = request.params.get('came_from') or "/%s"%ag.base
        return render('/login.html')

    def welcome(self):
        identity = request.environ.get("repoze.who.identity")
        came_from = request.params.get('came_from') or "/%s"%ag.base
        came_from = unquote(came_from)
        came_from = unquote(came_from)
        came_from = unquote(came_from)
        came_from = str(came_from)
        if identity:
            # Login succeeded
            userid = identity['repoze.who.userid']
            #user_det = get_mediator_details(userid)
            #if user_det['name']:
            #    session['user_name'] = user_det['name']
            #if user_det['uri']:
            #    session['user_uri'] = str(user_det['uri'])
            session['user_id'] = userid
            session.save()
            return redirect(url(came_from))
        else:
            # Login failed
            try:
                login_counter = request.environ['repoze.who.logins'] + 1
            except:
                login_counter = 0
            destination = "/%slogin?came_from=%s&logins=%s" % (ag.base,came_from, login_counter)
            return redirect(url(destination))

    def logout(self):
        c.userid = None
        c.message = "We hope to see you soon!"
        #display_message("We hope to see you soon!", status="success")
        came_from = request.params.get('came_from') or "/%s"%ag.base
        #came_from = request.params.get('came_from', '') or "/%s"%ag.base
        came_from = unquote(came_from)
        came_from = unquote(came_from)
        came_from = unquote(came_from)
        came_from = str(came_from)
        if session.has_key('user_name'):
            del session['user_name']
        if session.has_key('user_uri'):
            del session['user_uri']
        if session.has_key('user_id'):
            del session['user_id']
        if session.has_key('user_dept'):
            del session['user_dept']
        if session.has_key('user_email'):
            del session['user_email']
        session.save()
        #return render('/logout.html')
        #return redirect(url(came_from))
        return redirect(url("/"))
