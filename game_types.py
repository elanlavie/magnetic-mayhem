"""Registry of game types.

A game type is a complete way to play: it decides which room modes exist and
how a round feels. Every type uses the same tutor, so students always
earn progress by explaining their reasoning. Add a new type by adding an entry
here, then wiring its rules into the server.
"""

DEFAULT='station'

GAME_TYPES={
    'station':{'name':'Space station','icon':'🚀',
               'summary':'Among Us-style imposter missions, cooperative rescue, or a two-team race. Every task is a chat with the ship engineer.',
               'available':True,'modes':('solo','coop','race','infiltration','impostorSolo')},
    'climb':{'name':'Tower climb','icon':'🧗',
             'summary':'A jumping platformer. Hop up the tower, and every ledge gate is a question for the tutor. First to the summit wins the race.',
             'available':True,'modes':('solo','coop','race')},
    'chat':{'name':'Chat','icon':'💬','summary':'A plain back-and-forth with the tutor, one question at a time. Used for homework.',
            'available':True,'modes':('solo',),'hidden':True},
}

def public():
    return [{'id':k,'name':v['name'],'icon':v['icon'],'summary':v['summary'],'available':v['available']} for k,v in GAME_TYPES.items() if not v.get('hidden')]

def check(game_type,mode):
    """Return an error message if this type or mode can't be used, otherwise None."""
    info=GAME_TYPES.get(game_type)
    if not info:return 'Unknown game type.'
    if not info['available']:return f'{info["name"]} is not available yet.'
    if mode not in info['modes']:return 'This game type does not support that mode.'
    return None
