using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Media;

namespace Mazandasht.Presentation.Controls
{
    /// <summary>
    /// A bar chart drawn with nothing but WPF primitives.
    ///
    /// WHY NOT A CHARTING LIBRARY
    ///
    /// The owner runs this offline on Windows 8.1. Pulling in LiveCharts or
    /// OxyPlot means a NuGet binary that has to be present, loadable, and
    /// compatible with .NET Framework 4.8 on an OS Microsoft abandoned. If it
    /// fails, the owner sees an empty panel and has no way to fix it. Forty
    /// lines of OnRender cannot fail that way.
    ///
    /// WHAT IT DOES NOT DO
    ///
    /// No axes, no labels, no interaction, no animation. This is a comparison
    /// strip: bars scaled to the largest value, drawn right-to-left because the
    /// rest of the app is. Every number the owner needs is printed in the card
    /// above the bar; the bar only answers "which one is bigger".
    /// </summary>
    public sealed class MiniBarChart : FrameworkElement
    {
        public static readonly DependencyProperty ValuesProperty =
            DependencyProperty.Register(
                "Values", typeof(IList<double>), typeof(MiniBarChart),
                new FrameworkPropertyMetadata(null,
                    FrameworkPropertyMetadataOptions.AffectsRender));

        public static readonly DependencyProperty BarBrushProperty =
            DependencyProperty.Register(
                "BarBrush", typeof(Brush), typeof(MiniBarChart),
                new FrameworkPropertyMetadata(Brushes.Green,
                    FrameworkPropertyMetadataOptions.AffectsRender));

        public static readonly DependencyProperty BarGapProperty =
            DependencyProperty.Register(
                "BarGap", typeof(double), typeof(MiniBarChart),
                new FrameworkPropertyMetadata(4.0,
                    FrameworkPropertyMetadataOptions.AffectsRender));

        public IList<double> Values
        {
            get { return (IList<double>)GetValue(ValuesProperty); }
            set { SetValue(ValuesProperty, value); }
        }

        public Brush BarBrush
        {
            get { return (Brush)GetValue(BarBrushProperty); }
            set { SetValue(BarBrushProperty, value); }
        }

        public double BarGap
        {
            get { return (double)GetValue(BarGapProperty); }
            set { SetValue(BarGapProperty, value); }
        }

        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);

            // Transparent backdrop: without it a fully empty chart is not
            // hit-testable, which makes it feel broken during debugging.
            dc.DrawRectangle(Brushes.Transparent, null,
                new Rect(0, 0, ActualWidth, ActualHeight));

            IList<double> values = Values;
            if (values == null || values.Count == 0) return;
            if (ActualWidth <= 0 || ActualHeight <= 0) return;

            double max = 0;
            foreach (double v in values)
            {
                double a = Math.Abs(v);
                if (a > max) max = a;
            }
            if (max <= 0) return;

            int n = values.Count;
            double gap = BarGap;
            double slot = ActualWidth / n;
            double barWidth = slot - gap;
            if (barWidth < 1) barWidth = 1;

            Brush brush = BarBrush;

            for (int i = 0; i < n; i++)
            {
                double fraction = Math.Abs(values[i]) / max;
                if (fraction > 1) fraction = 1;
                double h = fraction * (ActualHeight - 2);
                if (h < 1 && values[i] != 0) h = 1;      // a tiny non-zero value
                                                          // must still be visible

                // Right-to-left: index 0 sits at the right edge.
                double x = ActualWidth - (i + 1) * slot + gap / 2;
                double y = ActualHeight - h;

                dc.DrawRoundedRectangle(brush, null,
                    new Rect(x, y, barWidth, h), 3, 3);
            }
        }
    }
}
