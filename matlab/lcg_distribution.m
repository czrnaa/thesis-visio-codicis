%% LCG Distribution Proof - Node Selection Frequency Chart

% extracted frequencies from the test reports.
% sorted from most frequent to least frequent
nodes = {
    'Marilao', 'Plaridel (Municipal Hall)', 'San Miguel', 'Plaridel', ...
    'San Miguel (Viola Street)', 'Balagtas', 'Bocaue (Crossing)', ...
    'Marilao (Municipal Hall)', 'Bocaue', 'Guiguinto', 'Guiguinto (Plaza)', ...
    'Calumpit (Market)', 'Paombong', 'Meycauayan', 'HQ Malolos', ...
    'Hagonoy', 'Malolos (City Hall)', 'Calumpit'
    };

frequencies = [47, 43, 42, 41, 40, 35, 34, 34, 33, 33, 31, 31, 28, 28, 28, 27, 26, 25];

c = categorical(nodes);
c = reordercats(c, nodes); 

figure('Name', 'LCG Distribution Proof', 'Color', 'white', 'Position', [100, 100, 950, 550]);

b = bar(c, frequencies, 'FaceColor', [0.17 0.32 0.51], 'EdgeColor', 'none', 'BarWidth', 0.65);

title('Frequency Distribution of LCG-Generated Test Scenarios', 'FontSize', 14, 'FontWeight', 'bold');
xlabel('Graph Node (Municipality/City/Landmark)', 'FontSize', 12, 'FontWeight', 'bold');
ylabel('Selection Frequency', 'FontSize', 12, 'FontWeight', 'bold');

ax = gca;
ax.FontSize = 11;
ax.YGrid = 'on';          
ax.GridLineStyle = '--';
ax.GridAlpha = 0.3;

xtickangle(45);

text(1:length(frequencies), frequencies + 1.2, num2str(frequencies'), ...
    'HorizontalAlignment', 'center', 'FontSize', 10, 'Color', [0.1 0.1 0.1], 'FontWeight', 'bold');