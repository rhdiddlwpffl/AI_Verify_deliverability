from app.db.session import connect_args_for


def test_session_pooler_keeps_default_prepared_statements():
    args = connect_args_for("postgresql://u:p@host.pooler.supabase.com:5432/postgres")
    assert args == {"connect_timeout": 5}


def test_transaction_pooler_disables_prepared_statements():
    # Transaction pooler(6543)에서는 준비된 쿼리를 끄지 않으면 요청이 간헐적으로 실패할 수 있다
    args = connect_args_for("postgresql://u:p@host.pooler.supabase.com:6543/postgres")
    assert args["prepare_threshold"] is None
    assert args["connect_timeout"] == 5


def test_url_without_port_or_garbage_does_not_crash():
    assert connect_args_for("postgresql://u:p@host/postgres") == {"connect_timeout": 5}
    assert connect_args_for("not a url") == {"connect_timeout": 5}
