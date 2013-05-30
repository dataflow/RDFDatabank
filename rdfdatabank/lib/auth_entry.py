# -*- coding: utf-8 -*-
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

from rdfdatabank.model import meta, User, Group, Permission, Datasets
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
#import traceback
#import logging
#log = logging.getLogger(__name__)

def add_silo(silo_name):
    try:
        p_q = meta.Session.query(Permission)
        
        ga = Group()
        if silo_name == '*':
            ga.group_name = u'databank_administrator'
        else:
            ga.group_name = u'%s_administrator'%silo_name
        ga.silo = u"%s"%silo_name
        meta.Session.add(ga)

        p_q_admin = p_q.filter(Permission.permission_name == u'administrator').one()
        p_q_admin.groups.append(ga)

        gb = Group()
        if silo_name == '*':
            gb.group_name = u'databank_manager'
        else:
            gb.group_name = u'%s_manager'%silo_name
        gb.silo = u"%s"%silo_name
        meta.Session.add(gb)

        p_q_manager = p_q.filter(Permission.permission_name == u'manager').one()
        p_q_manager.groups.append(gb)

        gc = Group()
        if silo_name == '*':
            gc.group_name = u'databank_submitter'
        else:
            gc.group_name = u'%s_submitter'%silo_name
        gc.silo = u'%s'%silo_name
        meta.Session.add(gc)

        p_q_submitter = p_q.filter(Permission.permission_name == u'submitter').one()
        p_q_submitter.groups.append(gc)

        meta.Session.commit()
    except IntegrityError:
        #log.error('Error adding new silo %s'%silo_name)
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def delete_silo(silo_name):
    try:
        # Delete all datasets in silo
        d_q = meta.Session.query(Datasets)
        d_q_id = d_q.filter(Datasets.silo == u'%s'%silo_name)
        for dataset in d_q_id:
            meta.Session.delete(dataset)
        # Delete silo
        g_q = meta.Session.query(Group)
        if silo_name == '*':
            g_q_group1 = g_q.filter(Group.group_name == u'databank_administrator').one()
            g_q_group2 = g_q.filter(Group.group_name == u'databank_manager').one()
            g_q_group3 = g_q.filter(Group.group_name == u'databank_submitter').one()
        else:
            g_q_group1 = g_q.filter(Group.group_name == u'%s_administrator'%silo_name).one()
            g_q_group2 = g_q.filter(Group.group_name == u'%s_manager'%silo_name).one()
            g_q_group3 = g_q.filter(Group.group_name == u'%s_submitter'%silo_name).one()
        meta.Session.delete(g_q_group1)
        meta.Session.delete(g_q_group2)
        meta.Session.delete(g_q_group3)
        meta.Session.commit()
    except (IntegrityError, NoResultFound, MultipleResultsFound):
        #log.error('Error deleting silo %s'%silo_name)
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def add_user(user_details):
    u = User()
    u.user_name = user_details['username']
    u._set_password(u'%s'%user_details['password'])

    if 'name' in user_details and user_details['name']:
        u.name = u'%s'%user_details['name']

    if 'firstname' in user_details and user_details['firstname']:
        u.firstname = u'%s'%user_details['firstname']

    if 'lastname' in user_details and user_details['lastname']:
        u.lastname = u'%s'%user_details['lastname']

    if 'email' in user_details and user_details['email']:
        u.email = u'%s'%user_details['email']
    try:
        meta.Session.add(u)
        meta.Session.commit()
    except IntegrityError:
        #log.error('Error adding user %s'%user_details['username'])
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def update_user(user_details):
    if not ('username' in user_details and user_details['username']):
        return False
    try:
        u_q = meta.Session.query(User)
        u = u_q.filter(User.user_name == u'%s'%user_details['username']).one()

        if 'password' in user_details and user_details['password']:
            u._set_password(u'%s'%user_details['password'])

        if 'name' in user_details and user_details['name']:
            u.name = u'%s'%user_details['name']

        if 'firstname' in user_details and user_details['firstname']:
            u.firstname = u'%s'%user_details['firstname']

        if 'lastname' in user_details and user_details['lastname']:
            u.lastname = u'%s'%user_details['lastname']

        if 'email' in user_details and user_details['email']:
            u.email = u'%s'%user_details['email']

        meta.Session.commit()
    except IntegrityError:
        #log.error('Error updating user data for user %s'%user_details['username'])
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def delete_user(username):
    try:
        u_q = meta.Session.query(User)
        u = u_q.filter(User.user_name == u'%s'%username).one()
        meta.Session.delete(u)
        meta.Session.commit()
    except (IntegrityError, NoResultFound, MultipleResultsFound):
        #log.error('Error deleting user %s. Does the user exist?'%username)
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def add_user_groups(username, groups):
    #groups is a list of (silo_name, permission_name) tuples
    try:
        u_q = meta.Session.query(User)
        u = u_q.filter(User.user_name == u'%s'%username).one()
        g_q = meta.Session.query(Group)
        for silo_name, permission_name in groups:
            if silo_name =='*':
                g_q_group = g_q.filter(Group.group_name == u'databank_%s'%permission_name).one()
            else:
                g_q_group = g_q.filter(Group.group_name == u'%s_%s'%(silo_name, permission_name)).one()
            u.groups.append(g_q_group)
        meta.Session.commit()
    except IntegrityError:
        #log.error('Error adding user %s to group %s'%(username, unicode(groups)))
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def delete_user_groups(username, groups): 
    #groups is a list of (silo_name, permission_name) tuples
    try:
        u_q = meta.Session.query(User)
        u = u_q.filter(User.user_name == u'%s'%username).one()
        g_q = meta.Session.query(Group)
        for silo_name, permission_name in groups:
            if silo_name =='*':
                g = g_q.filter(Group.group_name == u'databank_%s'%permission_name).one()
            else:
                g = g_q.filter(Group.group_name == u'%s_%s'%(silo_name, permission_name)).one()
            query = "DELETE FROM user_group WHERE user_id=%d and group_id=%d"%(u.id, g.id)
            meta.Session.execute(query)
        meta.Session.commit()
    except IntegrityError:
        #log.error('Error deleting user %s from group %s'%(username, unicode(groups)))
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def add_group_users(silo_name, user_groups):
    #user_groups is a list of (user_name, permission_name) tuples
    try:
        u_q = meta.Session.query(User)
        g_q = meta.Session.query(Group)
        for username, permission_name in user_groups:
            u = u_q.filter(User.user_name == u'%s'%username).one()
            if u:
                if silo_name =='*':
                    g_q_group = g_q.filter(Group.group_name == u'databank_%s'%permission_name).one()
                else:
                    g_q_group = g_q.filter(Group.group_name == u'%s_%s'%(silo_name, permission_name)).one()
                u.groups.append(g_q_group)
        meta.Session.commit()
    except IntegrityError:
        #log.error( 'Error adding users %s to group %s'%(unicode(user_groups), silo_name))
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def delete_group_users(silo_name, user_groups):
    #user_groups is a list of (user_name, permission_name) tuples
    try:
        u_q = meta.Session.query(User)
        g_q = meta.Session.query(Group)
        for username, permission_name in user_groups:
            u = u_q.filter(User.user_name == u'%s'%username).one()
            if silo_name =='*':
                g = g_q.filter(Group.group_name == u'databank_%s'%permission_name).one()
            else:
                g = g_q.filter(Group.group_name == u'%s_%s'%(silo_name, permission_name)).one()
            query = "DELETE FROM user_group WHERE user_id=%d and group_id=%d"%(u.id, g.id)
            meta.Session.execute(query)
        meta.Session.commit()
    except (IntegrityError, NoResultFound, MultipleResultsFound):
        #log.error('Error deleting users %s from group %s'%(unicode(user_groups), silo_name))
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def list_users():
    users = meta.Session.query(User)
    users_list = []
    for u in users:
        # print u.id, u.user_name, u.email, u.name, u.firstname, u.lastname
        # u._get_password
        user_details = {}
        user_details['user_name'] = u.user_name
        user_details['name'] = u.name
        user_details['firstname'] = u.firstname
        user_details['lastname'] = u.lastname
        user_details['email'] = u.email
        user_details['groups'] = []
        # groups user belongs to
        for g in u.groups:
            # print g.id, g.group_name, g.silo
            # permissions associated with the group
            for p in g.permissions:
                # print p.id, p.permission_name
                user_details['groups'].append((g.silo, p.permission_name))
        users_list.append(user_details)
    return users_list

def list_groups():
    groups = meta.Session.query(Group)
    #for g in groups:
    #    print g.id, g.group_name, g.silo
    #    permissions associated with the group
    #    for p in g.permissions:
    #        print p.id, p.permission_name
    return groups

def list_silos(star=False):
    silos = []
    groups = meta.Session.query(Group)
    for g in groups:
        if g.silo == "*" and star and not g.silo in silos:
            silos.append(g.silo)
        elif not g.silo in silos and g.silo != "*":
            silos.append(g.silo)
    return silos

def list_permissions():
    permissions = meta.Session.query(Permission)
    #for p in permissions:
    #    print p.id, p.permission_name
    return permissions

def list_usernames():
    users = meta.Session.query(User)
    usernames = []
    for u in users:
        usernames.append(u.user_name)
    return usernames

def list_user_permissions(username, siloname):
    u_q = meta.Session.query(User)
    u = u_q.filter(User.user_name == u'%s'%username).one()
    p_list = []
    #groups user belongs to
    for g in u.groups:
        if g.silo == siloname:
            #permissions associated with the group
            for p in g.permissions:
                p_list.append(p.permission_name)
    return p_list

def list_user_groups(username):
    u_q = meta.Session.query(User)
    u = u_q.filter(User.user_name == u'%s'%username).one()
    groups =[]
    for g in u.groups:
        for p in g.permissions:
            groups.append((g.silo, p.permission_name))
    return groups

def list_group_users(siloname):
    all_users = meta.Session.query(User)
    group_users =[]
    for u in all_users:
        for g in u.groups:
            if g.silo == siloname:
                #permissions associated with the group
                for p in g.permissions:
                    #TODO:Check if I am getting only those permission associated with the user and group
                    group_users.append({
                        'user_name':u.user_name,
                        'permission':p.permission_name,
                        'name':u.name,
                        'firstname':u.firstname,
                        'lastname':u.lastname})
    return group_users

def list_group_usernames(siloname):
    all_users = meta.Session.query(User)
    admins = []
    managers = []
    submitters = []
    for u in all_users:
        for g in u.groups:
            if g.silo == siloname:
                for p in g.permissions:
                    if p.permission_name == 'administrator' and not u.user_name in admins:
                        admins.append(u.user_name)
                    if p.permission_name == 'manager' and not u.user_name in managers:
                        managers.append(u.user_name)
                    if p.permission_name == 'submitter' and not u.user_name in submitters:
                        submitters.append(u.user_name)
    return (admins, managers, submitters)

def list_new_users():
    #Users not a part of any group
    all_users = meta.Session.query(User)
    ungrouped_users =[]
    for u in all_users:
        if not u.groups:
            ungrouped_users.append({
                'user_name':u.user_name,
                'permission':None,
                'name':u.name,
                'firstname':u.firstname,
                'lastname':u.lastname})
    return ungrouped_users

def list_user(username):
    u_q = meta.Session.query(User)
    u = u_q.filter(User.user_name == u'%s'%username).one()
    user_details = {}
    user_details['id'] = u.id
    user_details['user_name'] = u.user_name
    user_details['name'] = u.name
    user_details['firstname'] = u.firstname
    user_details['lastname'] = u.lastname
    user_details['email'] = u.email
    user_details['groups'] = []
    for g in u.groups:
        for p in g.permissions:
            user_details['groups'].append((g.silo, p.permission_name))
    return user_details

def add_dataset(silo_name, id):
    d = Datasets()
    d.silo = u"%s"%silo_name
    d.id = u"%s"%id
    try:
        meta.Session.add(d)
        meta.Session.commit()
    except IntegrityError:
        #log.error('Error adding dataset %s in silo %s'%(id, silo_name))
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def delete_dataset(silo_name, id):
    try:
        d_q = meta.Session.query(Datasets)
        d_q_id = d_q.filter(Datasets.silo == u'%s'%silo_name).filter(Datasets.id == u'%s'%id).one()
        meta.Session.delete(d_q_id)
        meta.Session.commit()
    except (IntegrityError, NoResultFound, MultipleResultsFound):
        #log.error('Error deleting dataset %s in silo %s'%(id, silo_name))
        #print traceback.format_exc()
        meta.Session.rollback()
        return False
    return True

def get_datasets_count(silo_name):
    d_q = meta.Session.query(Datasets)
    d_q_silo = d_q.filter(Datasets.silo == u'%s'%silo_name).count()
    return d_q_silo

def get_datasets(silo_name, start=0, rows=100):
    d_q = meta.Session.query(Datasets)
    try:
        start = int(start)
    except:
        start = 0
    try:
        rows = int(rows)
    except:
        rows = 100
    d_q_silo = d_q.filter(Datasets.silo == u'%s'%silo_name).limit(rows).offset(start).all()
    datasets = []
    for s in d_q_silo:
        datasets.append(s.id)
    return datasets

