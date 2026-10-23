#!/usr/bin/env swift
import AppKit
let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
for size in [16, 32, 64, 128, 256, 512, 1024] {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let scale = CGFloat(size) / 1024
    let transform = NSAffineTransform()
    transform.scale(by: scale)
    transform.concat()
    NSColor(calibratedRed: 0.06, green: 0.08, blue: 0.11, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 24, y: 24, width: 976, height: 976), xRadius: 210, yRadius: 210).fill()
    NSColor(calibratedRed: 0.42, green: 0.87, blue: 0.75, alpha: 1).setStroke()
    let path = NSBezierPath(); path.lineWidth = 40; path.lineCapStyle = .round; path.lineJoinStyle = .round
    let points: [(CGFloat, CGFloat)] = [(180,512),(270,512),(320,400),(380,720),(450,240),(520,800),(585,335),(650,630),(705,512),(844,512)]
    path.move(to: NSPoint(x: points[0].0, y: points[0].1))
    for point in points.dropFirst() { path.line(to: NSPoint(x: point.0, y: point.1)) }; path.stroke()
    NSGraphicsContext.restoreGraphicsState()
    let data = bitmap.representation(using: .png, properties: [:])!
    if size <= 512 && size != 64 { try data.write(to: output.appendingPathComponent("icon_\(size)x\(size).png")) }
    if size >= 32 { try data.write(to: output.appendingPathComponent("icon_\(size/2)x\(size/2)@2x.png")) }
}
