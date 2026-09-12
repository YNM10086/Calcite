package com.calcite.service.importer;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilderFactory;
import java.io.InputStream;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * GPX 解析器。
 *
 * <p>用 JDK 自带的 DOM，**不引入任何新依赖** —— 和项目里"手写 SVG 不装图表库"
 * 是同一个取舍。GPX 文件很小（实测 300 KB），一次性读进内存没问题。
 */
public class GpxImporter implements Importer {

    @Override
    public String format() {
        return "gpx";
    }

    @Override
    public ParsedTrack parse(InputStream in) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        // GPX 来自外部文件，必须关掉外部实体解析，否则存在 XXE 漏洞
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);

        Document doc = factory.newDocumentBuilder().parse(in);

        String name = firstTrkName(doc);

        List<RawPoint> points = new ArrayList<>();
        NodeList nodes = doc.getElementsByTagNameNS("*", "trkpt");
        for (int i = 0; i < nodes.getLength(); i++) {
            Element el = (Element) nodes.item(i);
            try {
                double lat = Double.parseDouble(el.getAttribute("lat"));
                double lon = Double.parseDouble(el.getAttribute("lon"));
                if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
                    continue; // 坐标越界，跳过
                }
                OffsetDateTime t = parseTime(firstChildText(el, "time"));
                if (t == null) {
                    continue; // 没有时间的点没法参与速度计算，跳过
                }
                points.add(new RawPoint(lat, lon, parseDoubleOrNull(firstChildText(el, "ele")), t));
            } catch (RuntimeException ignored) {
                // 单个坏点跳过，不影响整条轨迹
            }
        }

        if (points.isEmpty()) {
            throw new IllegalArgumentException("文件里没有有效的轨迹点");
        }
        return new ParsedTrack(name, points);
    }

    /** 取 {@code <trk><name>}；没有就返回 null（由服务层用文件名兜底） */
    private static String firstTrkName(Document doc) {
        NodeList trks = doc.getElementsByTagNameNS("*", "trk");
        for (int i = 0; i < trks.getLength(); i++) {
            String v = firstChildText((Element) trks.item(i), "name");
            if (v != null && !v.isBlank()) {
                return v.trim();
            }
        }
        return null;
    }

    /** 取直接子元素里第一个指定标签的非空文本；兼容带命名空间和不带命名空间两种写法 */
    private static String firstChildText(Element parent, String tag) {
        NodeList kids = parent.getChildNodes();
        for (int i = 0; i < kids.getLength(); i++) {
            Node n = kids.item(i);
            if (n.getNodeType() == Node.ELEMENT_NODE && tag.equals(n.getLocalName())) {
                String v = n.getTextContent();
                if (v != null && !v.isBlank()) {
                    return v.trim();
                }
            }
        }
        return null;
    }

    private static Double parseDoubleOrNull(String s) {
        if (s == null) {
            return null;
        }
        try {
            return Double.parseDouble(s);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static OffsetDateTime parseTime(String s) {
        if (s == null) {
            return null;
        }
        try {
            return OffsetDateTime.parse(s);
        } catch (RuntimeException e) {
            return null;
        }
    }
}
