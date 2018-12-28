# coding=utf8

from __future__ import print_function, division

import os
import csv
import ujson
import itchat
import datetime
from itchat.content import *
from collections import defaultdict

# todo: document dependencies with requirement file: ujson, itchat


class ScoreCard(object):
    def __init__(self):
        self.my_pval = 0
        self.opponent_pval = 0

    @property
    def my_ppct(self):
        return round(self.my_pval / (self.my_pval + self.opponent_pval) * 100, 2)

    @property
    def opponent_ppct(self):
        return round(self.opponent_pval / (self.my_pval + self.opponent_pval) * 100, 2)

    def __str__(self):
        return u'me {my_ppct}({my_pval}) VS {oppo_ppct}({oppo_pval}) opponent'.format(
            my_ppct=self.my_ppct,
            my_pval=self.my_pval,
            oppo_ppct=self.opponent_ppct,
            oppo_pval=self.opponent_pval
        )


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
    persist(msg, to_user_id_name)

    # handle p value inquiries
    if to_user_id_name == FILE_HELPER and 'pondness' in msg['Text'].lower():
        return notify_me(pprint_scorecards(scorecard_map))

    # I just sent a msg, that shows my interest, therefore bump my pondness value
    scorecard_map[to_user_id_name].my_pval += 1


def handle_incoming_msg(msg, from_user_id_name):
    log(u'I received a message {} from {}'.format(msg['Text'], get_user_human_name(user_id_name=from_user_id_name)))
    persist(msg, from_user_id_name)

    # Some sent me a msg, that shows their interest, therefore bump their pondness value
    scorecard_map[from_user_id_name].opponent_pval += 1


# --------------------------------------------- Helper Functions ---------------------------------------------------


def now():
    return datetime.datetime.now()


def log(msg):
    try:
        print(u'{} {}'.format(now(), msg))
    except Exception as e:
        print(str(e))


def persist(msg, who_am_i_talking_to):
    script_dir = os.path.dirname(__file__)
    rel_path = 'log/{}.csv'.format(who_am_i_talking_to)
    abs_file_path = os.path.join(script_dir, rel_path)

    with open(abs_file_path, 'a') as f:
        writer = csv.writer(f)
        writer.writerow([ujson.dumps(msg, ensure_ascii=False)])


def notify_me(msg):
    log(msg)
    itchat.send_msg(msg, FILE_HELPER)


def pprint_scorecards(score_card_map):
    arr = []
    for user_id_name, scorecard in score_card_map.items():
        arr.append(u'me {my_ppct}% VS {oppo_ppct}% {oppo_name}'.format(
            my_ppct=scorecard.my_ppct,
            oppo_ppct=scorecard.opponent_ppct,
            oppo_name=get_user_human_name(user_id_name=user_id_name),
        ))
    return '\n'.join(arr)


def send_img(msg, user_name):
    """ wrapper around itchat's weird way of image forwarding """
    msg['Text'](msg['FileName'])
    itchat.send_image(msg['FileName'], user_name)


def get_user_human_name(user=None, user_id_name=None):
    if user:
        return user['RemarkName'] or user['NickName'] or user['Name']
    elif user_id_name:
        user = itchat.search_friends(userName=user_id_name)
        if user:
            return get_user_human_name(user)
        else:
            # return back user id name in case no corresponding user can be found
            # this is at least happening for file helper
            return user_id_name
    else:
        return 'user not found'


def is_my_outgoing_msg(msg):
    return msg['FromUserName'] == MY_USER_ID_NAME


if __name__ == '__main__':
    itchat.auto_login()
    MY_USER_ID_NAME = itchat.get_friends(update=True)[0]["UserName"]
    itchat.run()
