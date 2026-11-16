from pydantic import SecretStr


def validate_password_rules(value: SecretStr) -> SecretStr:
    """校验注册及修改密码的统一规则，保留用户输入原样。"""
    password = value.get_secret_value()
    errors = []
    if not password:
        raise ValueError("请输入密码")
    if len(password) < 8:
        errors.append("密码至少需要 8 位")
    if len(password) > 20:
        errors.append("密码不能超过 20 位")
    if not any("A" <= char <= "Z" for char in password):
        errors.append("缺少大写字母")
    if not any("a" <= char <= "z" for char in password):
        errors.append("缺少小写字母")
    if not any("0" <= char <= "9" for char in password):
        errors.append("缺少数字")
    if any(char.isspace() or char == "\ufeff" for char in password):
        errors.append("密码不能包含空格或其他空白字符")
    if any(
        not "!" <= char <= "~" and not char.isspace() and char != "\ufeff"
        for char in password
    ):
        errors.append("密码只能包含英文字母、数字和英文符号，不能包含中文等字符")
    if errors:
        raise ValueError("；".join(errors))
    return value

