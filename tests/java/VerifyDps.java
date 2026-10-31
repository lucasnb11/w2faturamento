// Oráculo independente JSR-105 para documentos e certificados SINTÉTICOS.
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.crypto.dsig.XMLSignature;
import javax.xml.crypto.dsig.XMLSignatureFactory;
import javax.xml.crypto.dsig.Reference;
import javax.xml.crypto.dsig.dom.DOMValidateContext;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.nio.file.Files;
import java.nio.file.Path;
import org.w3c.dom.Element;

class VerifyDps {
    public static void main(String[] args) throws Exception {
        var factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute("http://javax.xml.XMLConstants/property/accessExternalDTD", "");
        factory.setAttribute("http://javax.xml.XMLConstants/property/accessExternalSchema", "");
        var doc = factory.newDocumentBuilder().parse(args[0]);
        var cert = (X509Certificate) CertificateFactory.getInstance("X.509")
            .generateCertificate(Files.newInputStream(Path.of(args[1])));
        var info = (Element) doc.getElementsByTagNameNS("http://www.sped.fazenda.gov.br/nfse", "infDPS").item(0);
        var node = doc.getElementsByTagNameNS(XMLSignature.XMLNS, "Signature").item(0);
        var context = new DOMValidateContext(cert.getPublicKey(), node);
        // Necessário apenas para conferir SHA-1 legado no teste sintético.
        context.setProperty("org.jcp.xml.dsig.secureValidation", false);
        context.setIdAttributeNS(info, null, "Id");
        var signatures = XMLSignatureFactory.getInstance("DOM");
        var resolver = signatures.getURIDereferencer();
        context.setURIDereferencer((reference, ctx) -> {
            if (!("#" + info.getAttribute("Id")).equals(reference.getURI()))
                throw new javax.xml.crypto.URIReferenceException("Referência externa bloqueada");
            return resolver.dereference(reference, ctx);
        });
        var signature = signatures.unmarshalXMLSignature(context);
        System.out.println("core=" + signature.validate(context));
        System.out.println("signature=" + signature.getSignatureValue().validate(context));
        for (var item : signature.getSignedInfo().getReferences())
            System.out.println("reference=" + ((Reference) item).validate(context));
    }
}
