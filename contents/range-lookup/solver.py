def solver(n):
    if n <= 1000000:
        return "Free"
    elif n <= 10000000:
        return "Pro"
    elif n <= 125000000:
        return "Business"
    elif n <= 500000000:
        return "Premium"
    else:
        return "担当SAにご相談ください"
