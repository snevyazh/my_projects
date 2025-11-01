from itertools import permutations
import operator
from itertools import product

numbers = [1, 5, 4, 8]
target = 81
ops = {
    '+': operator.add,
    '-': operator.sub,
    '*': operator.mul,
    '/': operator.truediv,
}

perm_symbol = list(product(ops.keys(), repeat=3))
perm_numbers = list(permutations(numbers, 4))


def get_result(number_a, number_b, operator):
    try:
        res = ops.get(operator)(number_a, number_b)
    except ZeroDivisionError:
        res = 0
    return res


found = False

for iteration, oper_sequence in enumerate(perm_symbol):
    for i, number_sequence in enumerate(perm_numbers):
        first_number = number_sequence[0]
        second_number = number_sequence[1]
        third_number = number_sequence[2]
        fourth_number = number_sequence[3]

        first_result = get_result(first_number, second_number, oper_sequence[0])
        for second_inputs in list(permutations([first_result, third_number], 2)):
            second_result = get_result(second_inputs[0], second_inputs[1], oper_sequence[1])
            for third_input in list(permutations([second_result, fourth_number], 2)):
                desired_sum = get_result(third_input[0], third_input[1], oper_sequence[2])
                if abs(desired_sum - target) < 1:
                    # this is for pretty print only
                    first_combina = f"({first_number} {oper_sequence[0]} {second_number})"
                    if second_inputs[0] in numbers:
                        second_combina = f"({second_inputs[0]} {oper_sequence[1]} {first_combina})"
                    else:
                        second_combina = f"({first_combina} {oper_sequence[1]} {second_inputs[0]})"
                    if third_input[0] in numbers:
                        third_combina = f"({third_input[0]} {oper_sequence[2]} {second_combina})"
                    else:
                        third_combina = f"({second_combina} {oper_sequence[2]} {third_input[0]})"
                    print(
                        f"SUM {desired_sum}. Operations: {third_combina}")
                    found = True
if not found:
    print("not found")
