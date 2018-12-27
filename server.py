# coding=utf8

from __future__ import print_function
import itchat
import datetime
from itchat.content import *
from collections import defaultdict


class ScoreCard(object):
    def __init__(self):
        self.my_pval = 0
        self.opponent_pval = 0


conversation_list = defaultdict(ScoreCard)

# --------------------------------------------- Handle Friend Chat ---------------------------------------------------


@itchat.msg_register([TEXT, PICTURE, FRIENDS, CARD, MAP, SHARING, RECORDING, ATTACHMENT, VIDEO], isFriendChat=True)
def text_reply(msg):
    """ handle robot switch and friends messages """
    to_user_name = msg['ToUserName']
    from_user_name = msg['FromUserName']

    to_user = itchat.search_friends(to_user_name)
    from_user = itchat.search_friends(from_user_name)

    if is_my_outgoing_msg(msg):
        handle_outgoing_msg(msg, to_user)
    else:  # this is an incoming message from my friend
        handle_incoming_msg(msg, from_user)


def handle_outgoing_msg(msg, to_user):
    user_name = get_user_display_name(to_user)
    log(u'I sent a message {} to {}'.format(msg['Text'], user_name))
    # todo: probably safer to use user id here
    # I just sent a msg, that shows my interest, therefore bump my pondness value
    conversation_list[user_name].my_pval += 1
    check_p_balance(conversation_list[user_name])


def handle_incoming_msg(msg, from_user):
    user_name = get_user_display_name(from_user)
    log(u'I received a message {} from {}'.format(msg['Text'], user_name))
    # todo: probably safer to use user id here
    # Some sent me a msg, that shows their interest, therefore bump their pondness value
    conversation_list[user_name].opponent_pval += 1
    check_p_balance(conversation_list[user_name])


def check_p_balance(score_card):
    log('my p-value: {}; opponent p-value: {}'.format(score_card.my_pval, score_card.opponent_pval))
    if score_card.my_pval < score_card.opponent_pval - 10:
        log(u'If you are interested, you might want to display it more openly')
    elif score_card.my_pval - 10 > score_card.opponent_pval:
        log(u'Hey slow down a little bit, you want to give him/her some time to catch up')

# --------------------------------------------- Helper Functions ---------------------------------------------------


def now():
    return datetime.datetime.now()


def log(msg):
    try:
        print(u'{} {}'.format(now(), msg))
    except Exception as e:
        print(str(e))


def send_img(msg, user_name):
    """ wrapper around itchat's weird way of image forwarding """
    msg['Text'](msg['FileName'])
    itchat.send_image(msg['FileName'], user_name)


def get_user_display_name(user=None, user_id_name=None):
    if user:
        return user['RemarkName'] or user['NickName'] or user['Name']
    elif user_id_name:
        return get_user_display_name(user=itchat.search_friends(userName=user_id_name))
    else:
        return 'user not found'


def is_my_outgoing_msg(msg):
    return msg['FromUserName'] == my_user_name()


def my_user_name():
    return itchat.get_friends(update=True)[0]["UserName"]


if __name__ == '__main__':
    itchat.auto_login()
    itchat.run()
