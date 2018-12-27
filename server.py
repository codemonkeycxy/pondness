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

    def __str__(self):
        return u'my p-value: {}; his/her p-value: {}'.format(self.my_pval, self.opponent_pval)


FILE_HELPER = 'filehelper'
scorecard_map = defaultdict(ScoreCard)

# --------------------------------------------- Handle Friend Chat ---------------------------------------------------


@itchat.msg_register([TEXT, PICTURE, FRIENDS, CARD, MAP, SHARING, RECORDING, ATTACHMENT, VIDEO], isFriendChat=True)
def text_reply(msg):
    """ handle robot switch and friends messages """
    to_user_id_name = msg['ToUserName']
    from_user_id_name = msg['FromUserName']

    if is_my_outgoing_msg(msg):
        handle_outgoing_msg(msg, to_user_id_name)
    else:  # this is an incoming message from my friend
        handle_incoming_msg(msg, from_user_id_name)


def handle_outgoing_msg(msg, to_user_id_name):
    log(u'I sent a message {} to {}'.format(msg['Text'], get_user_human_name(user_id_name=to_user_id_name)))

    # handle p value inquiries
    if to_user_id_name == FILE_HELPER and 'pondness' in msg['Content'].lower():
        return notify_me(pprint_scorecards(scorecard_map))

    # I just sent a msg, that shows my interest, therefore bump my pondness value
    scorecard_map[to_user_id_name].my_pval += 1
    check_p_balance(scorecard_map[to_user_id_name])


def handle_incoming_msg(msg, from_user_id_name):
    log(u'I received a message {} from {}'.format(msg['Text'], get_user_human_name(user_id_name=from_user_id_name)))
    # Some sent me a msg, that shows their interest, therefore bump their pondness value
    scorecard_map[from_user_id_name].opponent_pval += 1
    check_p_balance(scorecard_map[from_user_id_name])


def check_p_balance(scorecard):
    log(str(scorecard))
    if scorecard.my_pval < scorecard.opponent_pval - 10:
        notify_me(u'If you are interested, you might want to display it more openly')
    elif scorecard.my_pval - 10 > scorecard.opponent_pval:
        notify_me(u'Hey slow down a little bit, you want to give him/her some time to catch up')

# --------------------------------------------- Helper Functions ---------------------------------------------------


def now():
    return datetime.datetime.now()


def log(msg):
    try:
        print(u'{} {}'.format(now(), msg))
    except Exception as e:
        print(str(e))


def notify_me(msg):
    log(msg)
    itchat.send_msg(msg, FILE_HELPER)


def pprint_scorecards(score_card_map):
    arr = []
    for user_id_name, score_card in score_card_map.items():
        arr.append(u'{}: {}; me: {}'.format(
            get_user_human_name(user_id_name=user_id_name),
            score_card.opponent_pval,
            score_card.my_pval)
        )
    return '\n\n'.join(arr)


def send_img(msg, user_name):
    """ wrapper around itchat's weird way of image forwarding """
    msg['Text'](msg['FileName'])
    itchat.send_image(msg['FileName'], user_name)


def get_user_human_name(user=None, user_id_name=None):
    if user:
        return user['RemarkName'] or user['NickName'] or user['Name']
    elif user_id_name:
        return get_user_human_name(user=itchat.search_friends(userName=user_id_name))
    else:
        return 'user not found'


def is_my_outgoing_msg(msg):
    return msg['FromUserName'] == my_user_name()


def my_user_name():
    return itchat.get_friends(update=True)[0]["UserName"]


if __name__ == '__main__':
    itchat.auto_login()
    itchat.run()
