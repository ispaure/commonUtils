import SwiftUI

/// Presentation only: no storage, scheduling, networking, or application lifecycle.
struct WidgetValueView: View {
    let title: String
    let value: String
    let detail: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Text(value)
                .font(.system(size: 48, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .minimumScaleFactor(0.25)
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let detail {
                Text(detail).font(.caption2).foregroundStyle(.secondary).lineLimit(3)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}
