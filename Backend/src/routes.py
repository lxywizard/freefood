import json
import re
from db import db, User, Event
from flask import Flask, request
import helpers
import users_dao

db_filename = "ff.db"
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///%s' % db_filename
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True

db.init_app(app)
with app.app_context():
    db.create_all()


def extract_token(request):
    auth_header = request.headers.get('Authorization')
    if auth_header is None:
        return False, json.dumps({'error': 'Missing authorization header.'})

    # Header looks like "Authorization: Bearer <session token>"
    bearer_token = auth_header.replace('Bearer ', '').strip()
    if bearer_token is None or not bearer_token:
        return False, json.dumps({'error': 'Invalid authorization header.'})

    return True, bearer_token


@app.route('/')
def hello_world():
    return json.dumps({'message': 'Hello, World!'})


@app.route('/register/', methods=['POST'])
def register_account():
    post_body = json.loads(request.data)
    email = post_body.get('email')
    password = post_body.get('password')
    username = post_body.get('username')

    if email is None or password is None:
        return json.dumps({'error': 'Invalid email or password'})

    created, user = users_dao.create_user(email, password, username)

    if not created:
        return json.dumps({'error': 'User already exists.'})

    return json.dumps({
        'session_token': user.session_token,
        'session_expiration': str(user.session_expiration),
        'update_token': user.update_token
    })


@app.route('/login/', methods=['POST'])
def login():
    post_body = json.loads(request.data)
    email = post_body.get('email')
    password = post_body.get('password')

    if email is None or password is None:
        return json.dumps({'error': 'Invalid email or password'})

    success, user = users_dao.verify_credentials(email, password)

    if not success:
        return json.dumps({'error': 'Incorrect email or password.'})

    return json.dumps({
        'session_token': user.session_token,
        'session_expiration': str(user.session_expiration),
        'update_token': user.update_token
    })


@app.route('/session/', methods=['POST'])
def update_session():
    success, update_token = extract_token(request)

    if not success:
        return update_token

    try:
        user = users_dao.renew_session(update_token)
    except:
        return json.dumps({'error': 'Invalid update token.'})

    return json.dumps({
        'session_token': user.session_token,
        'session_expiration': str(user.session_expiration),
        'update_token': user.update_token
    })


@app.route('/secret/', methods=['GET'])
def secret_message():
    success, session_token = extract_token(request)

    if not success:
        return session_token

    user = users_dao.get_user_by_session_token(session_token)
    if not user or not user.verify_session_token(session_token):
        return json.dumps({'error': 'Invalid session token.'})

    return json.dumps({
        'message': 'You have successfully implemented sessions.',
        'username': user.username
    })


@app.route('/api/')
def hello_world_again():
    return json.dumps({'message': 'Hello, World!'})


@app.route('/api/', methods=['POST'])
def post_test_events():
    post_body = json.loads(request.data)
    print(post_body.get('content'))
    if helpers.has_food(post_body.get('content')):
        name = post_body.get('name')
        location = post_body.get('location')
        datetime = post_body.get('datetime')
        content = post_body.get('content')
        longitude = post_body.get('longitude')
        latitude = post_body.get('latitude')
        event = Event(name=name, location=location, datetime=datetime, content=content, longitude = longitude, latitude=latitude)
        db.session.add(event)
        db.session.commit()
        return json.dumps({'success': True, 'data': event.serialize()})
    else:
        return json.dumps({'success': False, 'error': 'No food offered in event!'}), 406


# post the events to our database based on events json returned by fbgraph
@app.route('/api/fromfb/', methods=['POST'])
def post_fb_events():
    post_body = json.loads(request.data)
    if helpers.has_food(post_body.get('description')):
        name = post_body.get('name')
        location = post_body.get('place')['name']
        starttime = post_body.get('start_time')
        start = re.split(r'T', starttime)
        datetime = start[0] + ' ' + re.match(r'\d{2}.\d{2}', start[1]).group()
        content = post_body.get('description')
        longitude = str(post_body.get('place')['location']['longitude'])
        latitude = str(post_body.get('place')['location']['latitude'])
        event = Event(name=name, location=location, datetime=datetime, content=content, longitude = longitude, latitude=latitude)
        db.session.add(event)
        db.session.commit()
        return json.dumps({'success': True, 'data': event.serialize()})
    else:
        return json.dumps({'success': False, 'error': 'No food offered in event!'}), 406


@app.route('/api/user/events/', methods=['GET'])
def get_events():
    success, session_token = extract_token(request)

    if not success:
        return session_token

    user = users_dao.get_user_by_session_token(session_token)
    if not user.verify_session_token(session_token):
        return json.dumps({'error': 'Invalid session token.'})
    
    if not user:
        return json.dumps({'error': 'Invalid User'})
    events = [event.serialize() for event in user.event]
    return json.dumps({
        'success': True,
        'data': events
    })


@app.route('/api/user/events/', methods=['POST'])
def post_event():
    success, session_token = extract_token(request)

    if not success:
        return session_token

    user = users_dao.get_user_by_session_token(session_token)
    if not user.verify_session_token(session_token):
        return json.dumps({'error': 'Invalid session token.'})

    if not user:
        return json.dumps({'error': 'Invalid User'})
    post_body = json.loads(request.data)
    if helpers.has_food(post_body.get('content')):
        event_id = post_body.get('id')
        event = Event.query.filter_by(id=event_id).first()
        user.event.append(event)
        db.session.commit()
        return json.dumps({'success': True, 'data': event.serialize()})
    else:
        return json.dumps({'success': False, 'error': 'No food offered in event!'}), 406


@app.route('/api/events/<int:event_id>/', methods=['DELETE'])
def delete_event(event_id):
    event = Event.query.filter_by(id=event_id).first()
    if not event:
        return json.dumps({'success': False, 'error': 'Event not found!'}), 404
    db.session.delete(event)
    db.session.commit()
    return json.dumps({'success': True, 'data': event.serialize()})


@app.route('/api/user/events/<int:event_id>/', methods=['DELETE'])
def delete_user_event(event_id):
    success, session_token = extract_token(request)

    if not success:
        return session_token

    user = users_dao.get_user_by_session_token(session_token)
    if not user.verify_session_token(session_token):
        return json.dumps({'error': 'Invalid session token.'})
    if not user:
        return json.dumps({'success': False, 'error': 'User not found!'}), 404
    event = Event.query.filter_by(id=event_id).first()
    if not event:
        return json.dumps({'success': False, 'error': 'Event not found!'}), 404
    user.event.remove(event)
    db.session.commit()
    return json.dumps({'success': True, 'data': event.serialize()})


@app.route('/api/events/', methods=['POST'])
def post_events():
    post_body = json.loads(request.data)
    for data in post_body.get('data'):
        if helpers.has_food(data.get('content')):    
            name = data.get('name')
            location = data.get('location')
            datetime = data.get('datetime')
            content = data.get('content')
            longitude = data.get('longitude')
            latitude = data.get('latitude')
            event = Event(name=name, location=location, datetime=datetime, content=content, longitude = longitude, latitude=latitude)
            db.session.add(event)
    db.session.commit()
    return json.dumps({'success': True, 'data': event.serialize()})


@app.route('/api/events/', methods=['GET'])
def get_all_events():
    events = Event.query.all()
    res = {'data': [event.serialize() for event in events]}
    return json.dumps(res), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
