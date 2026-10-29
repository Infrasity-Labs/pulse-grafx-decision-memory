"""The ten recall questions and the decision each one should reach. Fixed before the first run.
Questions are worded without the exact words of the decision titles. They are not tuned after results."""

QUESTIONS = [
    (1, "How do clients send their login token on each request, and what prefix does the server expect?", "auth-header-scheme"),
    (2, "How long does a login token stay valid before it expires?", "token-expiry"),
    (3, "What does the app use to store user passwords safely?", "password-hashing"),
    (4, "What does the body of an error response look like when a request fails?", "error-response-shape"),
    (5, "Which query parameters control paging through a list of articles?", "pagination-parameters"),
    (6, "How is the URL-friendly name of an article produced?", "slug-rules"),
    (7, "Who is allowed to delete a comment?", "comment-ownership"),
    (8, "What happens when a user marks an article as a favourite?", "favorites"),
    (9, "Where does the app keep its settings and how are they read?", "settings-loading"),
    (10, "How are the automated tests laid out?", "test-layout"),
]
