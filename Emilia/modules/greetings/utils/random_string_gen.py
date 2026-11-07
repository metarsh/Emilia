import random
import string

_RANDOM = random.SystemRandom()


def RandomStringGen() -> list:
    choices = set()
    while len(choices) < 12:
        choices.add("".join(_RANDOM.choices(string.ascii_lowercase + string.digits, k=7)))
    result = list(choices)
    _RANDOM.shuffle(result)
    return result


def mathCaptchaGen():
    num01 = _RANDOM.randint(1, 40)
    num02 = _RANDOM.randint(41, 80)
    answer = num01 + num02

    answer_dict = {"num01": num01, "num02": num02, "answer": answer}

    mathCaptchaList = _RANDOM.sample([value for value in range(1, 131) if value != answer], 11)
    mathCaptchaList.append(answer)
    _RANDOM.shuffle(mathCaptchaList)
    return answer_dict, mathCaptchaList
