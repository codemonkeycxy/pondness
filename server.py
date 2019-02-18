# coding=utf8

from __future__ import print_function, division

import os
import csv
import re
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
        self.their_pval = 0

    @property
    def my_ppct(self):
        return round(self.my_pval / (self.my_pval + self.their_pval) * 100, 2)

    @property
    def their_ppct(self):
        return round(self.their_pval / (self.my_pval + self.their_pval) * 100, 2)

    def __str__(self):
        return u'me {my_ppct}({my_pval}) VS {their_ppct}({their_pval}) them'.format(
            my_ppct=self.my_ppct,
            my_pval=self.my_pval,
            their_ppct=self.their_ppct,
            their_pval=self.their_pval
        )


FILE_HELPER = 'filehelper'

ONE_MIN = 60
TEN_MIN = 10 * 60
HALF_HOUR = 30 * 60
ONE_DAY = 24 * 60 * 60

# --------------------------------------------- Point Tally Strategy -------------------------------------------------


def ping_pong_tally(user_name, msg_logs, scorecard_map):
    """The most naive tally strategy. Each message contributes ONE pondness point"""
    for row in msg_logs:
        msg = ujson.loads(row[0])
        if is_my_outgoing_msg(msg):
            # I sent a msg, that shows my interest, therefore bump my pondness value
            scorecard_map[user_name].my_pval += 1
        else:  # this is an incoming message from my friend
            # Someone sent me a msg, that shows their interest, therefore bump their pondness value
            scorecard_map[user_name].their_pval += 1


def streak_bonus_tally(user_name, msg_logs, scorecard_map):
    """
    If a conversation participant sends multiple messages in a roll, give a small but cumulative bonus per message
    """
    my_streak_factor = 0
    their_streak_factor = 0

    for row in msg_logs:
        msg = ujson.loads(row[0])
        if is_my_outgoing_msg(msg):
            # I sent a msg, that shows my interest, therefore bump my pondness value with applicable streak bonus
            scorecard_map[user_name].my_pval += 0.1 * my_streak_factor
            my_streak_factor += 1
            their_streak_factor = 0
        else:  # this is an incoming message from my friend
            # Someone sent me a msg, that shows their interest,
            # therefore bump their pondness value with applicable streak bonus
            scorecard_map[user_name].their_pval += 0.1 * their_streak_factor
            their_streak_factor += 1
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
            if (is_prev_msg_outgoing and msg_ts - prev_msg_ts > HALF_HOUR) or msg_ts - prev_msg_ts > ONE_DAY:
                # I initiated a conversation, bump my p value
                scorecard_map[user_name].my_pval += 2
        else:
            if (not is_prev_msg_outgoing and msg_ts - prev_msg_ts > HALF_HOUR) or msg_ts - prev_msg_ts > ONE_DAY:
                # Someone initiated a conversation, bump their p value
                scorecard_map[user_name].their_pval += 2

        prev_msg_ts = msg_ts
        is_prev_msg_outgoing = is_my_outgoing_msg(msg)


def voice_message_tally(user_name, msg_logs, scorecard_map):
    """If someone sends a voice message instead of text, that shows extra interest"""
    for row in msg_logs:
        msg = ujson.loads(row[0])
        if is_my_outgoing_msg(msg):
            if msg['Type'] == RECORDING:
                # I sent a voice msg, that shows my interest, therefore bump my pondness value
                scorecard_map[user_name].my_pval += 1
        else:  # this is an incoming message from my friend
            if msg['Type'] == RECORDING:
                # Someone sent me a voice msg, that shows their interest, therefore bump their pondness value
                scorecard_map[user_name].their_pval += 1


def repeating_char_tally(user_name, msg_logs, scorecard_map):
    """If the message contains >3 repeating characters, that shows fondness"""
    for row in msg_logs:
        msg = ujson.loads(row[0])
        content = msg['Text']

        # emojis are written with multiple characters but we want to treat them as one unit
        # this line replaces emojis with a special character for easy counting
        content = re.sub(r'\[[a-zA-Z]+\]', '@', content)

        max_char, cnt = get_max_repeating_char(content)
        if cnt < 3 or max_char in [' ', '.', '。', '-', '_', '+', '=', ',', '`', '*', '|', '\\']:
            continue

        if is_my_outgoing_msg(msg):
            scorecard_map[user_name].my_pval += 0.1 * (cnt - 2)
        else:  # this is an incoming message from my friend
            scorecard_map[user_name].their_pval += 0.1 * (cnt - 2)

def lightening_reply_tally(user_name, msg_logs, scorecard_map):
    """
    Reward reply made within 1 min. The faster the reply is, the more pondness points are rewarded
    """
    if not msg_logs:
        return

    prev_msg_ts = 0
    is_prev_msg_outgoing = is_my_outgoing_msg(ujson.loads(msg_logs[0][0]))

    for row in msg_logs:
        msg = ujson.loads(row[0])
        msg_ts = msg['CreateTime']
        time_delta = msg_ts - prev_msg_ts

        if is_my_outgoing_msg(msg):
            if not is_prev_msg_outgoing and time_delta <= ONE_MIN:
                # I replied quickly, bump my p value
                scorecard_map[user_name].my_pval += (60 - time_delta) / 120
        else:
            if is_prev_msg_outgoing and time_delta <= ONE_MIN:
                # Someone replied quickly, bump their p value
                scorecard_map[user_name].their_pval += (60 - time_delta) / 120

        prev_msg_ts = msg_ts
        is_prev_msg_outgoing = is_my_outgoing_msg(msg)

def snail_reply_tally(user_name, msg_logs, scorecard_map):
    """
    Penalize reply made after 10 min. The slower the reply is, the more pondness points are deducted
    """
    if not msg_logs:
        return

    prev_msg_ts = 0
    is_prev_msg_outgoing = is_my_outgoing_msg(ujson.loads(msg_logs[0][0]))

    for row in msg_logs:
        msg = ujson.loads(row[0])
        msg_ts = msg['CreateTime']
        time_delta = msg_ts - prev_msg_ts

        if is_my_outgoing_msg(msg):
            if not is_prev_msg_outgoing and time_delta >= TEN_MIN:
                # I replied slowly, reduce my p value
                scorecard_map[user_name].my_pval -= min(0.1 * (time_delta / TEN_MIN), 2)
        else:
            if is_prev_msg_outgoing and time_delta >= TEN_MIN:
                # Someone replied slowly, reduce their p value
                scorecard_map[user_name].their_pval -= min(0.1 * (time_delta / TEN_MIN), 2)

        prev_msg_ts = msg_ts
        is_prev_msg_outgoing = is_my_outgoing_msg(msg)


TALLY_STRATEGIES = [
    ping_pong_tally,
    streak_bonus_tally,
    conversation_initiator_tally,
    voice_message_tally,
    repeating_char_tally,
    lightening_reply_tally,
    snail_reply_tally,
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

        if 'all' not in msg['Text'].lower():
            # default to pick the 10 most frequently talked to users
            # https://stackoverflow.com/questions/7197315/5-maximum-values-in-a-python-dictionary
            scorecard_map = dict(sorted(
                scorecard_map.iteritems(),
                key=lambda (k, v): v.my_pval + v.their_pval,
                reverse=True
            )[:10])

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


# https://www.geeksforgeeks.org/maximum-consecutive-repeating-character-string/
def get_max_repeating_char(string):
    total_len = len(string)
    count = 1
    max_char = string[0]

    # Find the maximum repeating
    # character starting from str[i]
    for i in range(total_len):
        cur_count = 1
        for j in range(i + 1, total_len):

            if string[i].lower() != string[j].lower():
                break
            cur_count += 1

        # Update result if required
        if cur_count > count:
            count = cur_count
            max_char = string[i]

    return max_char, count


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
        arr.append(u'me {my_ppct}% VS {their_ppct}% {their_name}'.format(
            my_ppct=scorecard.my_ppct,
            their_ppct=scorecard.their_ppct,
            their_name=user_name,
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
