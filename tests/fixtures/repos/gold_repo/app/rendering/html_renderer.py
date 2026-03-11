def select(options, key):
    return options[key]


class Session:
    def execute(self, value):
        return value


def render(value):
    session = Session()
    return session.execute(select({"html": value}, "html"))
