# coding=utf8

from __future__ import print_function, division

import os
import csv
import ujson
import itchat
import datetime
from itchat.content import *
from collections import defaultdict

# stupid python encode workarounds
# https://stackoverflow.com/questions/21129020/how-to-fix-unicodedecodeerror-ascii-codec-cant-decode-byte
import sys
reload(sys)
sys.setdefaultencoding('utf8')
###########

# todo: document dependencies with requirement file: ujson, itchat
# todo: replace raw percentage numbers with a progress bar
# https://stackoverflow.com/questions/3173320/text-progress-bar-in-the-console
# https://stackoverflow.com/questions/3160699/python-progress-bar


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

# --------------------------------------------- Point Tally Strategy -------------------------------------------------


def ping_pong_tally(user_name, msg_logs, scorecard_map):
    """The most naive tally strategy. Each message contributes ONE pondness point"""
    for row in msg_logs:
        msg = ujson.loads(row[0])
        if is_my_outgoing_msg(msg):
            # I sent a msg, that shows my interest, therefore bump my pondness value
            scorecard_map[user_name].my_pval += 1
        else:  # this is an incoming message from my friend
            # Some sent me a msg, that shows their interest, therefore bump their pondness value
            scorecard_map[user_name].opponent_pval += 1


def streak_bonus_tally(user_name, msg_logs, scorecard_map):
    """
    If a conversation participant sends multiple messages in a roll, give a small but cumulative bonus per message
    """
    my_streak_factor = 0
    opponent_streak_factor = 0

    for row in msg_logs:
        msg = ujson.loads(row[0])
        if is_my_outgoing_msg(msg):
            # I sent a msg, that shows my interest, therefore bump my pondness value with applicable streak bonus
            scorecard_map[user_name].my_pval += 0.1 * my_streak_factor
            my_streak_factor += 1
            opponent_streak_factor = 0
        else:  # this is an incoming message from my friend
            # Someone sent me a msg, that shows their interest,
            # therefore bump their pondness value with applicable streak bonus
            scorecard_map[user_name].opponent_pval += 0.1 * opponent_streak_factor
            opponent_streak_factor += 1
            my_streak_factor = 0


def conversation_initiator_tally(user_name, msg_logs, scorecard_map):
    """
    Give a bonus to the conversation initiator because that shows descent interest.

    However, it's hard to differentiate a conversation initiator from a delayed response. So for now we use a simple
    proxy:
    1. if two messages from the same person are >30min apart, assume the second message as a conversation initiator
    2. if two messages (regardless from whom) are >1day apart, assume the second message as a conversation initiator
    """
    if not msg_logs:
        return

    prev_msg_ts = 0
    is_prev_msg_outgoing = is_my_outgoing_msg(ujson.loads(msg_logs[0][0]))

    for row in msg_logs:
        msg = ujson.loads(row[0])
        msg_ts = msg['CreateTime']

        if is_my_outgoing_msg(msg):
            if (is_prev_msg_outgoing and msg_ts - prev_msg_ts > 30 * 60) or msg_ts - prev_msg_ts > 24 * 60 * 60:
                # I initiated a conversation, bump my p value
                scorecard_map[user_name].my_pval += 2
        else:
            if (not is_prev_msg_outgoing and msg_ts - prev_msg_ts > 30 * 60) or msg_ts - prev_msg_ts > 24 * 60 * 60:
                # Someone initiated a conversation, bump their p value
                scorecard_map[user_name].opponent_pval += 2

        prev_msg_ts = msg_ts
        is_prev_msg_outgoing = is_my_outgoing_msg(msg)


TALLY_STRATEGIES = [
    ping_pong_tally,
    streak_bonus_tally,
    conversation_initiator_tally,
]

# --------------------------------------------- Handle Friend Chat ---------------------------------------------------


@itchat.msg_register([TEXT, PICTURE, FRIENDS, CARD, MAP, SHARING, RECORDING, ATTACHMENT, VIDEO], isFriendChat=True)
def text_reply(msg):
    """ handle robot switch and friends messages """
    if msg['Type'] != TEXT:
        # sanitize the text field so that we can assume it always contains string.
        # and this is also to avoid infinite loop during serialization in the persist function
        msg['Text'] = msg['Type']

    to_user_id_name = msg['ToUserName']
    from_user_id_name = msg['FromUserName']

    if is_my_outgoing_msg(msg):
        handle_outgoing_msg(msg, to_user_id_name)
    else:  # this is an incoming message from my friend
        handle_incoming_msg(msg, from_user_id_name)


def handle_outgoing_msg(msg, to_user_id_name):
    user_human_name = get_user_human_name(user_id_name=to_user_id_name)
    log(u'I sent a message {} to {}'.format(msg['Text'], user_human_name))

    # handle p value inquiries
    if to_user_id_name == FILE_HELPER and 'pondness' in msg['Text'].lower():
        scorecard_map = collect_scorecards()
        return notify_me(pprint_scorecards(scorecard_map))

    persist(msg, user_human_name)


def handle_incoming_msg(msg, from_user_id_name):
    user_human_name = get_user_human_name(user_id_name=from_user_id_name)
    log(u'I received a message {} from {}'.format(msg['Text'], user_human_name))
    persist(msg, user_human_name)


def collect_scorecards():
    log_folder_path = get_log_folder_path()
    log_files = [f for f in os.listdir(log_folder_path) if f.endswith('.csv')]
    scorecard_map = defaultdict(ScoreCard)

    for log_file in log_files:
        user_name = log_file.replace('.csv', '')
        abs_file_path = os.path.join(log_folder_path, log_file)

        with open(abs_file_path, 'rt') as f:
            read = csv.reader(f)
            rows = [row for row in read]
            for tally_strategy in TALLY_STRATEGIES:
                tally_strategy(user_name, rows, scorecard_map)

    return scorecard_map


# --------------------------------------------- Helper Functions ---------------------------------------------------


def now():
    return datetime.datetime.now()


def log(msg):
    try:
        print(u'{} {}'.format(now(), msg))
    except Exception as e:
        print(str(e))


def get_log_folder_path():
    script_dir = os.path.dirname(__file__)
    return os.path.join(script_dir, 'log')


def persist(msg, who_am_i_talking_to):
    file_name = u'{}.csv'.format(who_am_i_talking_to)
    abs_file_path = os.path.join(get_log_folder_path(), file_name)

    with open(abs_file_path, 'a') as f:
        writer = csv.writer(f)
        writer.writerow([ujson.dumps(dict(msg), ensure_ascii=False)])


def notify_me(msg):
    log(msg)
    itchat.send_msg(msg, FILE_HELPER)


def pprint_scorecards(scorecard_map):
    arr = []
    for user_name, scorecard in scorecard_map.items():
        arr.append(u'me {my_ppct}% VS {oppo_ppct}% {oppo_name}'.format(
            my_ppct=scorecard.my_ppct,
            oppo_ppct=scorecard.opponent_ppct,
            oppo_name=user_name,
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
    return msg['ToUserName'] == msg['User']['UserName']


if __name__ == '__main__':
    itchat.auto_login(enableCmdQR=2)
    itchat.run()
