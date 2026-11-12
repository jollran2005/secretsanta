"""Small Discord-like objects used by assignment tests."""


class MockMember:
    def __init__(self, user_id, name):
        self.id = user_id
        self.display_name = name
        self.bot = False
