class FakeApi:
    def __init__(self):
        self.calls = []
        self.responses = {}

    def respond(self, method, endpoint, payload, status=200):
        self.responses[(method, endpoint)] = (payload, status)

    def __call__(self, method, endpoint, data=None, token=None):
        self.calls.append(
            {
                "method": method,
                "endpoint": endpoint,
                "data": data,
                "token": token,
            }
        )
        key = (method, endpoint)
        if key not in self.responses:
            raise AssertionError(f"Unexpected API call: {method} {endpoint}")
        return self.responses[key]
