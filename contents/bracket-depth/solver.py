def solver(s):
    stack = []
    pairs = {")": "(", "}": "{", "]": "["}
    max_depth = 0
    for char in s:
        if char in "({[":
            stack.append(char)
            max_depth = max(max_depth, len(stack))
        elif char in ")}]":
            if not stack or stack[-1] != pairs[char]:
                return -1
            stack.pop()
    return -1 if stack else max_depth
