import statistics
# for chapter 4 and 5 only

def get_user_input(metric_name):
    """Prompts the user to input data for a specific metric."""
    while True:
        try:
            print(f"\nEnter the 10 values for [{metric_name}] separated by spaces:")
            user_string = input(">>> ")
            data_list = [float(x) for x in user_string.split()]
            
            if len(data_list) != 10:
                print(f"Warning: You entered {len(data_list)} values instead of 10. Let's try again.")
                continue
            return data_list
        except ValueError:
            print("Error: Please enter numbers only, separated by single spaces.")

def calculate_and_display_metrics(data_list, metric_name):
    """Computes and formats the academic statistics."""
    mean_val = statistics.mean(data_list)
    median_val = statistics.median(data_list)
    # Using sample standard deviation (Bessel's correction n-1)
    std_dev_val = statistics.stdev(data_list) 
    worst_case_val = max(data_list)
    
    print(f"\n=========================================")
    print(f" STATISTICAL RESULTS: {metric_name.upper()}")
    print(f"=========================================")
    print(f"Mean (μ):            {mean_val:.2f}")
    print(f"Median (x̃):          {median_val:.2f}")
    print(f"Standard Dev (σ):    {std_dev_val:.2f}")
    print(f"Worst-Case (Max):    {worst_case_val:.2f}")
    print(f"=========================================")

time_data = get_user_input("Computational Time (ms)")
calculate_and_display_metrics(time_data, "Computational Time (ms)")

nodes_data = get_user_input("Nodes Explored")
calculate_and_display_metrics(nodes_data, "Nodes Explored")

optimality_data = get_user_input("Path Optimality Ratio")
calculate_and_display_metrics(optimality_data, "Path Optimality Ratio")
