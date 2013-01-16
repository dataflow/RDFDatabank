from rdfdatabank.lib.utils import allowable_id2, create_new
from rdfdatabank.lib.auth_entry import list_silos, add_dataset
from sss import SwordServer, Authenticator, Auth, ServiceDocument, SDCollection, DepositResponse, SwordError, EntryDocument, Statement, Namespaces, AuthException
from sss.negotiator import AcceptParameters, ContentType

from pylons import app_globals as ag

import uuid, re, logging, urllib
from datetime import datetime
from rdflib import URIRef

ssslog = logging.getLogger(__name__)

JAILBREAK = re.compile("[\/]*\.\.[\/]*")

class SwordDataBank(SwordServer):
    """
    The main SWORD Server class.  This class deals with all the CRUD requests as provided by the web.py HTTP
    handlers
    """
    def __init__(self, config, auth):
        # get the configuration
        self.config = config
        self.auth_credentials = auth
        
        self.um = URLManager(config)
        self.ns = Namespaces()

    def container_exists(self, path):
        # extract information from the path
        silo, dataset_id, accept_parameters = self.um.interpret_path(path)
        
        # is this a silo?
        if not ag.granary.issilo(silo):
            return False

        # is this an authorised silo?
        silos = ag.authz(self.auth_credentials.identity)
        if silo not in silos:
            return False
        
        # get a full silo object
        rdf_silo = ag.granary.get_rdf_silo(silo)
        
        # is the dataset in the authorised silo?
        if not rdf_silo.exists(dataset_id):
            return False
        
        # if we get here without failing, then the container exists (from the
        # perspective of the user)
        return True

    def media_resource_exists(self, path):
        raise NotImplementedError()

    def service_document(self, path=None):
        """
        Construct the Service Document.  This takes the set of collections that are in the store, and places them in
        an Atom Service document as the individual entries
        """
        service = ServiceDocument(version=self.config.sword_version,
                                    max_upload_size=self.config.max_upload_size)
        
        # get the authorised list of silos
        silos = ag.authz(self.auth_credentials.identity)
        
        # now for each collection create an sdcollection
        collections = []
        for col_name in silos:        
            href = self.um.silo_url(col_name)
            title = col_name
            mediation = self.config.mediation
            
            # content types accepted
            accept = []
            multipart_accept = []
            if not self.config.accept_nothing:
                if self.config.app_accept is not None:
                    for acc in self.config.app_accept:
                        accept.append(acc)
                
                if self.config.multipart_accept is not None:
                    for acc in self.config.multipart_accept:
                        multipart_accept.append(acc)
                        
            # SWORD packaging formats accepted
            accept_package = []
            for format in self.config.sword_accept_package:
                accept_package.append(format)
            
            col = SDCollection(href=href, title=title, accept=accept, multipart_accept=multipart_accept,
                                accept_package=accept_package, mediation=mediation)
                                
            collections.append(col)
        
        service.add_workspace("Silos", collections)

        # serialise and return
        return service.serialise()

    def list_collection(self, path):
        """
        List the contents of a collection identified by the supplied id
        """
        raise NotImplementedError()

    def _get_authorised_rdf_silo(self, silo):
    
        if not ag.granary.issilo(silo):
            return SwordError(status=404, empty=True)
    
        # get the authorised list of silos
        #granary_list = ag.granary.silos
        granary_list = list_silos()
        silos = ag.authz(self.auth_credentials.identity)
        
        # does the collection/silo exist?  If not, we can't do a deposit
        if silo not in silos:
            # if it's not in the silos it is either non-existant or it is
            # forbidden...
            if silo in granary_list:
                # forbidden
                raise SwordError(status=403, empty=True)
            else:
                # not found
                raise SwordError(status=404, empty=True)
        
        # get a full silo object
        rdf_silo = ag.granary.get_rdf_silo(silo)
        return rdf_silo
    
    def deposit_new(self, silo, deposit):
        """
        Take the supplied deposit and treat it as a new container with content to be created in the specified collection
        Args:
        -collection:    the ID of the collection to be deposited into
        -deposit:       the DepositRequest object to be processed
        Returns a DepositResponse object which will contain the Deposit Receipt or a SWORD Error
        """
        # check against the authorised list of silos
        rdf_silo = self._get_authorised_rdf_silo(silo)

        # ensure that we have a slug
        if deposit.slug is None:
            deposit.slug = str(uuid.uuid4())
            
        # weed out unacceptable deposits
        if rdf_silo.exists(deposit.slug):
            raise SwordError(error_uri=DataBankErrors.dataset_conflict, msg="A Dataset with the name " + deposit.slug + " already exists")
        if not allowable_id2(deposit.slug):
            raise SwordError(error_uri=Errors.bad_request, msg="Dataset name can contain only the following characters - " + 
                                                                ag.naming_rule_humanized + " and has to be more than 1 character")
        
        # NOTE: we pass in an empty dictionary of metadata on create, and then run
        # _ingest_metadata to augment the item from the deposit
        item = create_new(rdf_silo, deposit.slug, self.auth_credentials.username, {})
        add_dataset(silo, deposit.slug)
        self._ingest_metadata(item, deposit)
        
        # NOTE: left in for reference for the time being, but deposit_new 
        # only support entry only deposits in databank.  This will need to be
        # re-introduced for full sword support
        # store the content file if one exists, and do some processing on it
        #deposit_uri = None
        #derived_resource_uris = []
        #if deposit.content is not None:
        
       #     if deposit.filename is None:
       #         deposit.filename = "unnamed.file"
       #     fn = self.dao.store_content(collection, id, deposit.content, deposit.filename)

            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want
            
            # FIXME: because the deposit interpreter doesn't deal with multipart properly
            # we don't get the correct packaging format here if the package is anything
            # other than Binary
       #     ssslog.info("attempting to load ingest packager for format " + str(deposit.packaging))
       #     packager = self.configuration.get_package_ingester(deposit.packaging)(self.dao)
       #     derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)

            # An identifier which will resolve to the package just deposited
       #     deposit_uri = self.um.part_uri(collection, id, fn)
            
            # a list of identifiers which will resolve to the derived resources
       #     derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)

        # the aggregation uri
        agg_uri = self.um.agg_uri(silo, deposit.slug)

        # the Edit-URI
        edit_uri = self.um.edit_uri(silo, deposit.slug)

        # create the initial statement
        s = Statement(aggregation_uri=agg_uri, rem_uri=edit_uri, states=[DataBankStates.initial_state])
        
        # FIXME: need to sort out authentication before we can do this ...
        # FIXME: also, it's not relevant unless we take a binary-only deposit, which
        # we currently don't
        # User already authorized to deposit in this silo (_get_authorised_rdf_silo). 
        # This is to augment metadata with details like who created, on behalf of, when
        #
        #by = deposit.auth.username if deposit.auth is not None else None
        #obo = deposit.auth.on_behalf_of if deposit.auth is not None else None
        #if deposit_uri is not None:
        #    s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
        #s.aggregates = derived_resource_uris

        # In creating the statement we use the existing manifest.rdf file in the
        # item:
        manifest = item.get_rdf_manifest()
        f = open(manifest.filepath, "r")
        rdf_string = f.read()

        # create the new manifest and store it
        #Serialize rdf adds the sword statement - state, depositedOn, by, onBehalfOf, stateDesc
        new_manifest = s.serialise_rdf(rdf_string)
        item.put_stream("manifest.rdf", new_manifest)

        # FIXME: here is where we have to put the correct treatment in
        # now generate a receipt for the deposit
        # TODO: Add audit log from item.manifest in place of  "created new item"
        receipt = self.deposit_receipt(silo, deposit.slug, item, "created new item")

        # FIXME: while we don't have full text deposit, we don't need to augment
        # the deposit receipt
        
        # now augment the receipt with the details of this particular deposit
        # this handles None arguments, and converts the xml receipt into a string
        # receipt = self.augmented_receipt(receipt, deposit_uri, derived_resource_uris)
        
        # finally, assemble the deposit response and return
        dr = DepositResponse()
        dr.receipt = receipt.serialise()
        dr.location = receipt.edit_uri
        
        # Broadcast change as message
        ag.b.creation(silo, deposit.slug, ident=self.auth_credentials.username)
        
        return dr

    def get_media_resource(self, path, accept_parameters):
        """
        Get a representation of the media resource for the given id as represented by the specified content type
        -id:    The ID of the object in the store
        -content_type   A ContentType object describing the type of the object to be retrieved
        """
        raise NotImplementedError()
    
    def replace(self, path, deposit):
        """
        Replace all the content represented by the supplied id with the supplied deposit
        Args:
        - oid:  the object ID in the store
        - deposit:  a DepositRequest object
        Return a DepositResponse containing the Deposit Receipt or a SWORD Error
        """
        silo, dataset_id, accept_parameters = self.um.interpret_path(path)
        rdf_silo = self._get_authorised_rdf_silo(silo)
            
        # now get the dataset object itself
        dataset = rdf_silo.get_item(dataset_id)
        
        # deal with possible problems with the filename
        if deposit.filename is None or deposit.filename == "":
            raise SwordError(error_uri=Errors.bad_request, msg="You must supply a filename to unpack")
        if JAILBREAK.search(deposit.filename) != None:
            raise SwordError(error_uri=Errors.bad_request, msg="'..' cannot be used in the path or as a filename")
        
        # FIXME: at the moment this metadata operation is not supported by DataBank
        #
        # first figure out what to do about the metadata
        keep_atom = False
        metadata_state = None # This will be used to store any state information associated
                                # with a metadata update.  It gets tied up with the content state
                                # and any pre-existing states further down
        #if deposit.atom is not None:
        #    ssslog.info("Replace request has ATOM part - updating")
        #    entry_ingester = self.configuration.get_entry_ingester()(self.dao)
        #    entry_ingester.ingest(collection, id, deposit.atom)
        #    keep_atom = True
        
        content_state = None
        deposit_uri = None
        derived_resource_uris = []
        if deposit.content_file is not None:
            ssslog.info("Replace request has file content - updating")
            
            # remove all the old files before adding the new.  We always leave
            # behind the metadata; this will be overwritten later if necessary
            #self.dao.remove_content(collection, id, True, keep_atom)
            #Increment the version, but do not clone the previous version.
            # An update will replace the entire contents of the container (if previously unpacked) with the bagit file
            dataset.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])

            # store the content file
            dataset.put_stream(deposit.filename, deposit.content_file)
            ssslog.debug("New incoming file stored with filename " + deposit.filename)
            
            # FIXME: unpacking doesn't happen here ... (keeping for the time being for reference)
            # Broadcast to unpack and add sword:state in manifest
            # <sword:state rdf:resource="http://purl.org/net/sword/state/queuedForUnpacking"/>
            
            # now that we have stored the atom and the content, we can invoke a package ingester over the top to extract
            # all the metadata and any files we want.  Notice that we pass in the metadata_relevant flag, so the
            # packager won't overwrite the existing metadata if it isn't supposed to
            #packager = self.configuration.get_package_ingester(deposit.packaging)(self.dao)
            #derived_resources = packager.ingest(collection, id, fn, deposit.metadata_relevant)
            #ssslog.debug("Resources derived from deposit: " + str(derived_resources))
        
            # a list of identifiers which will resolve to the derived resources
            #derived_resource_uris = self.get_derived_resource_uris(collection, id, derived_resources)

            # An identifier which will resolve to the package just deposited
            deposit_uri = self.um.file_uri(silo, dataset_id, deposit.filename)
            ssslog.debug("Incoming file has been stored at URI " + deposit_uri)
            
            # register a new content state to be used
            content_state = DataBankStates.zip_file_added

        # Taken from dataset.py, seems to be the done thing when adding an item.
        # NOTE: confirmed with Anusha that this is correct
        dataset.del_triple(dataset.uri, u"dcterms:modified")
        dataset.add_triple(dataset.uri, u"dcterms:modified", datetime.now())
        dataset.del_triple(dataset.uri, u"oxds:currentVersion")
        dataset.add_triple(dataset.uri, u"oxds:currentVersion", dataset.currentversion)

        # before we do any state management, we have to be sure that the sword namespace
        # is registered
        dataset.get_rdf_manifest().add_namespace("sword", "http://purl.org/net/sword/terms/")
        dataset.sync()
        
        # sort out the new list of states for the item
        current_states = self._extract_states(dataset)
        new_states = []
        
        # for each existing state, consider whether to carry it over
        ssslog.info("new content state: " + str(content_state))
        for state_uri, state_desc in current_states:
            keep = True
            if metadata_state is not None and state_uri in DataBankStates.metadata_states:
                # we do not want the state if it is a metadata state and we have been given
                # a new metadata state
                keep = False
            if content_state is not None and state_uri in DataBankStates.content_states:
                    ssslog.debug("Removing state: " + state_uri)
                    # we do not want the state if it is a content state and we have been given
                    # a new content state
                    keep = False            
            if keep:
                ssslog.debug("carrying over state: " + state_uri)
                new_states.append((state_uri, state_desc))
        
        # add the new metadata and content states provided from above
        if metadata_state is not None:
            new_states.append(metadata_state)
        if content_state is not None:
            ssslog.debug("adding new content state: " + str(content_state))
            new_states.append(content_state)
            
        ssslog.debug("New Dataset States: " + str(new_states))
        
        # FIXME: how safe is this?  What other ore:aggregates might there be?
        # we need to back out some of the triples in preparation to update the
        # statement
        # NOTE AR: I have commented the following lines. 
        #       For aggregates this is not needed. put_stream will add the aggregate into the URI. 
        #       Why delete other triples in the manifest - ??
        # sword:originalDeposit point to isVersionOf
        
        aggregates = dataset.list_rdf_objects(dataset.uri, u"ore:aggregates")
        original_deposits = dataset.list_rdf_objects(dataset.uri, u"sword:originalDeposit")
        states = dataset.list_rdf_objects(dataset.uri, u"sword:state")
        
        for a in aggregates:
            dataset.del_triple(a, "*")
        for od in original_deposits:
            dataset.del_triple(od, "*")
        for s in states:
            dataset.del_triple(s, "*")
        dataset.del_triple(dataset.uri, u"ore:aggregates")
        dataset.del_triple(dataset.uri, u"sword:originalDeposit")
        dataset.del_triple(dataset.uri, u"sword:state")

        # FIXME: also unsafe in the same way as above
        # Write the md5 checksum into the manifest
        # A deposit contains just the new stuff so no harm in deleting all triples 
        dataset.del_triple("*", u"oxds:hasMD5")
        #dataset.del_triple(deposit_uri, u"oxds:hasMD5")
        if deposit.content_md5 is not None:
            dataset.add_triple(deposit_uri, u"oxds:hasMD5", deposit.content_md5)
        
        dataset.sync()

        # the aggregation uri
        agg_uri = self.um.agg_uri(silo, dataset_id)

        # the Edit-URI
        edit_uri = self.um.edit_uri(silo, dataset_id)

        # FIXME: here we also need to keep existing states where relevant.
        #   A state will continue to be relevant if it applies to an area of the
        #   item (i.e. the container or the media resource) for which this operation
        #   has no effect.
        #   for example:
        #   this is a metadata replace, but a status on the item is set to say that
        #   the item's zip file is corrupt and needs replacing.  The new status 
        #   should leave this alone (and probably not do anything, tbh), no matter
        #   what else it does
        # create the statement outline
        # FIXME: there is something weird going on with instantiating this object without the original_deposits argument
        # apparently if I don't explicitly say there are no original deposits, then it "remembers" original deposits 
        # from previous uses of the object
        s = Statement(aggregation_uri=agg_uri, rem_uri=edit_uri, states=new_states, original_deposits=[])
         
        # set the original deposit (which sorts out the aggregations for us too)
        by = deposit.auth.username if deposit.auth is not None else None
        obo = deposit.auth.on_behalf_of if deposit.auth is not None else None
        if deposit_uri is not None:
            s.original_deposit(deposit_uri, datetime.now(), deposit.packaging, by, obo)
        
        # create the new manifest and store it
        manifest = dataset.get_rdf_manifest()
        f = open(manifest.filepath, "r")
        rdf_string = f.read()
        
        new_manifest = s.serialise_rdf(rdf_string)
        dataset.put_stream("manifest.rdf", new_manifest)
        
        # FIXME: add in proper treatment here
        # now generate a receipt. 
        # TODO: Include audit log instead of 'added zip to dataset'
        receipt = self.deposit_receipt(silo, dataset_id, dataset, "added zip to dataset")
        
        # now augment the receipt with the details of this particular deposit
        # this handles None arguments, and converts the xml receipt into a string
        receipt = self.augmented_receipt(receipt, deposit_uri, derived_resource_uris)

        # finally, assemble the deposit response and return
        dr = DepositResponse()
        dr.receipt = receipt.serialise()
        dr.location = receipt.edit_uri
        return dr

    def delete_content(self, path, delete):
        """
        Delete all of the content from the object identified by the supplied id.  the parameters of the delete
        request must also be supplied
        - oid:  The ID of the object to delete the contents of
        - delete:   The DeleteRequest object
        Return a DeleteResponse containing the Deposit Receipt or the SWORD Error
        """
        raise NotImplementedError()
        
    def add_content(self, path, deposit):
        """
        Take the supplied deposit and treat it as a new container with content to be created in the specified collection
        Args:
        -collection:    the ID of the collection to be deposited into
        -deposit:       the DepositRequest object to be processed
        Returns a DepositResponse object which will contain the Deposit Receipt or a SWORD Error
        """
        raise NotImplementedError()

    def get_container(self, path, accept_parameters):
        """
        Get a representation of the container in the requested content type
        Args:
        -oid:   The ID of the object in the store
        -content_type   A ContentType object describing the required format
        Returns a representation of the container in the appropriate format
        """
        # by the time this is called, we should already know that we can return this type, so there is no need for
        # any checking, we just get on with it

        ssslog.info("Container requested in mime format: " + accept_parameters.content_type.mimetype())
        silo, dataset_id, _ = self.um.interpret_path(path)
        rdf_silo = self._get_authorised_rdf_silo(silo)
        
        # now get the dataset object itself
        dataset = rdf_silo.get_item(dataset_id)

        # pick either the deposit receipt or the pure statement to return to the client
        if accept_parameters.content_type.mimetype() == "application/atom+xml;type=entry":
            # Supply audit log as treatment, in place of 'no treatment'
            receipt = self.deposit_receipt(silo, dataset_id, dataset, "no treatment") # FIXME: what should the treatment here be
            return receipt.serialise()
        # FIXME: at the moment we don't support conneg on the edit uri
        #elif accept_parameters.content_type.mimetype() == "application/rdf+xml":
        #    return self.dao.get_statement_content(collection, id)
        #elif accept_parameters.content_type.mimetype() == "application/atom+xml;type=feed":
        #    return self.dao.get_statement_feed(collection, id)
        else:
            ssslog.info("Requested mimetype not recognised/supported: " + accept_parameters.content_type.mimetype())
            return None

    def deposit_existing(self, path, deposit):
        """
        Deposit the incoming content into an existing object as identified by the supplied identifier
        Args:
        -oid:   The ID of the object we are depositing into
        -deposit:   The DepositRequest object
        Returns a DepositResponse containing the Deposit Receipt or a SWORD Error
        """
        raise NotImplementedError()

    def delete_container(self, path, delete):
        """
        Delete the entire object in the store
        Args:
        -oid:   The ID of the object in the store
        -delete:    The DeleteRequest object
        Return a DeleteResponse object with may contain a SWORD Error document or nothing at all
        """
        raise NotImplementedError()

    def get_statement(self, path):
        silo, dataset_id, accept_parameters = self.um.interpret_path(path)
        rdf_silo = self._get_authorised_rdf_silo(silo)
            
        # now get the dataset object itself
        dataset = rdf_silo.get_item(dataset_id)
        
        if accept_parameters.content_type.mimetype() == "application/rdf+xml":
            return self.get_rdf_statement(dataset)
        elif accept_parameters.content_type.mimetype() == "application/atom+xml;type=feed":
            return self.get_atom_statement(dataset)
        else:
            return None

    # NOT PART OF STANDARD, BUT USEFUL    
    # These are used by the webpy interface to provide easy access to certain
    # resources.  Not implementing them is fine.  If they are not implemented
    # then you just have to make sure that your file paths don't rely on the
    # Part http handler
    
    def get_part(self, path):
        """
        Get a file handle to the part identified by the supplied path
        - path:     The URI part which is the path to the file
        """
        raise NotImplementedError()
        
    def get_edit_uri(self, path):
        raise NotImplementedError()
    
    def get_rdf_statement(self, dataset):
        # The RDF statement is just the manifest file...
        manifest = dataset.get_rdf_manifest()
        f = open(manifest.filepath, "r")
        return f.read()
        
    def get_atom_statement(self, dataset):
        # FIXME: there isn't a requirement at this stage to support the atom
        # statment for DataBank
        return None
        
    def deposit_receipt(self, silo, identifier, item, treatment, verbose_description=None):
        """
        Construct a deposit receipt document for the provided URIs
        Returns an EntryDocument object
        """
        # FIXME: we don't know what the item's API looks like yet; it's probably
        # from somewhere within RecordSilo or Pairtree.  Suck it and see ...
        
        # assemble the URIs we are going to need
        
        # the atom entry id
        drid = self.um.atom_id(silo, identifier)

        # the Cont-URI
        cont_uri = self.um.cont_uri(silo, identifier)

        # the EM-URI 
        em_uri = self.um.em_uri(silo, identifier)
        em_uris = [(em_uri, None), (em_uri + ".atom", "application/atom+xml;type=feed")]

        # the Edit-URI and SE-IRI
        edit_uri = self.um.edit_uri(silo, identifier)
        se_uri = edit_uri

        # the splash page URI
        splash_uri = self.um.html_url(silo, identifier)

        # the two statement uris
        atom_statement_uri = self.um.state_uri(silo, identifier, "atom")
        ore_statement_uri = self.um.state_uri(silo, identifier, "ore")
        state_uris = [(atom_statement_uri, "application/atom+xml;type=feed"), (ore_statement_uri, "application/rdf+xml")]

        # ensure that there is a metadata object, and that it is populated with enough information to build the
        # deposit receipt
        dc_metadata, other_metadata = self._extract_metadata(item)
        ssslog.debug("Incorporating metadata: " + str(dc_metadata))
        if dc_metadata is None:
            dc_metadata = {}
        if not dc_metadata.has_key("title"):
            dc_metadata["title"] = ["SWORD Deposit"]
        if not dc_metadata.has_key("creator"):
            dc_metadata["creator"] = ["SWORD Client"]
        if not dc_metadata.has_key("abstract"):
            dc_metadata["abstract"] = ["Content deposited with SWORD client"]

        packaging = []
        for disseminator in self.config.sword_disseminate_package:
            packaging.append(disseminator)

        # Now assemble the deposit receipt
        dr = EntryDocument(atom_id=drid, alternate_uri=splash_uri, content_uri=cont_uri,
                            edit_uri=edit_uri, se_uri=se_uri, em_uris=em_uris,
                            packaging=packaging, state_uris=state_uris, dc_metadata=dc_metadata,
                            verbose_description=verbose_description, treatment=treatment)

        return dr
    
    # FIXME: currently this only deals with DC metadata as per the SWORD spec.
    # If possible, we should extract other metadata from the item too, but since
    # it is in RDF it's not so obvious how best to do it.  Just pull out rdf
    # terms?
    def _extract_metadata(self, item):
        graph = item.get_graph()
        dc_metadata = {}
        other_metadata = {}
        # we're just going to focus on DC metadata, to comply with the SWORD
        # spec
        dc_offset = len(self.ns.DC_NS)
        
        for s, p, o in graph.triples((URIRef(item.uri), None, None)):
            if p.startswith(self.ns.DC_NS):
                # it is Dublin Core
                field = p[dc_offset:]
                if dc_metadata.has_key(field):
                    dc_metadata[field].append(o)
                else:
                    dc_metadata[field] = [o]
        return dc_metadata, other_metadata
        
    def augmented_receipt(self, receipt, original_deposit_uri, derived_resource_uris=[]):
        receipt.original_deposit_uri = original_deposit_uri
        receipt.derived_resource_uris = derived_resource_uris     
        return receipt
        
    def _ingest_metadata(self, item, deposit):
        ed = deposit.get_entry_document()
        entry_ingester = self.config.get_entry_ingester()()
        entry_ingester.ingest(item, ed)
        
    def _extract_states(self, dataset):
        states = []
        state_uris = dataset.list_rdf_objects(dataset.uri, u"sword:state")
        for su in state_uris:
            descriptions = dataset.list_rdf_objects(su, u"sword:stateDescription")
            sd = None
            if len(descriptions) > 0:
                sd = str(descriptions[0]) # just take the first one, there should only be one
            states.append((str(su), sd))
        return states

class DefaultEntryIngester(object):
    def __init__(self):
        self.ns = Namespaces()
        
        # FIXME: could we put this into configuration?
        #           or we could define handlers for each element rather than
        #           just a field to put the value in.  This will allow us to
        #           handle hierarchical metadata (e.g. atom:author), but without
        #           having to go down the route of building XSLT xwalks
        # FIXME: a fuller treatment of atom metadata may be appropriate here
        self.metadata_map = {
            self.ns.ATOM + "title" : u"dcterms:title",
            self.ns.ATOM + "summary" : u"dcterms:abstract"
        }
        # NOTE: much atom metadata is hierarchical so this approach may
        # not work
        
    def ingest(self, item, entry, additive=False):
        ssslog.debug("Ingesting Metadata; Additive? " + str(additive))
        
        ssslog.debug("Non DC Metadata: " + str(entry.other_metadata))
        for element in entry.other_metadata:
            if not self.metadata_map.has_key(element.tag):
                # FIXME: only process metadata we recognise
                ssslog.debug("skipping unrecognised metadata: " + element.tag)
                continue
            if element.text is not None:
                item.add_triple(item.uri, self.metadata_map[element.tag], element.text.strip())
        
        # explicitly handle the DC
        for dc, values in entry.dc_metadata.iteritems():
            for v in values:
                item.add_triple(item.uri, u"dcterms:" + dc, v)
        
        item.sync()

class DataBankAuthenticator(Authenticator):
    def __init__(self, config): 
        self.config = config
        
    def basic_authenticate(self, username, password, obo):
        # In [AtomPub] Section 14, implementations MUST support HTTP Basic Authentication 
        # in conjunction with a TLS connection. The SWORD Profile relaxes this requirement: 
        # SWORD client and server implementations SHOULD be capable of being configured to 
        # use HTTP Basic Authentication [RFC2617] in conjunction with a TLS connection 
        # as specified by [RFC2818].
        
        # FIXME: basic authentication does not attempt to actually authenticate
        # anyone, it simply rejects any such request.  This is in-line with SWORD
        # above, but it would be better if it did authenticate.
        
        # Nonetheless, in general, databank will use repoze for everything including
        # HTTP basic, so this method should never be activated
        #return Auth(username, obo)
        raise AuthException(authentication_failed=True, msg="HTTP Basic Auth without repoze.who not permitted on this server")
        
    def repoze_who_authenticate(self, identity, obo):
        # the authentication is actually already done, so all we need to do is
        # populate the Auth object
        return DataBankAuth(identity["repoze.who.userid"], obo, identity)

class DataBankAuth(Auth):
    def __init__(self, username, on_behalf_of, identity):
        Auth.__init__(self, username, on_behalf_of)
        self.identity = identity
 
class URLManager(object):
    def __init__(self, config):
        self.config = config
        
    def silo_url(self, silo):
        return self.config.base_url + "silo/" + urllib.quote(silo)
        
    def atom_id(self, silo, identifier):
        return "tag:container@databank/" + urllib.quote(silo) + "/" + urllib.quote(identifier)
        
    def cont_uri(self, silo, identifier):
        return self.config.base_url + "edit-media/" + urllib.quote(silo) + "/" + urllib.quote(identifier)
        
    def em_uri(self, silo, identifier):
        """ The EM-URI """
        return self.config.base_url + "edit-media/" + urllib.quote(silo) + "/" + urllib.quote(identifier)
        
    def edit_uri(self, silo, identifier):
        """ The Edit-URI """
        return self.config.base_url + "edit/" + urllib.quote(silo) + "/" + urllib.quote(identifier)
    
    def agg_uri(self, silo, identifier):
        return self.config.db_base_url + urllib.quote(silo) + "/datasets/" + urllib.quote(identifier)
    
    def html_url(self, silo, identifier):
        """ The url for the HTML splash page of an object in the store """
        return self.agg_uri(silo, identifier)
    
    def state_uri(self, silo, identifier, type):
        root = self.config.base_url + "statement/" + urllib.quote(silo) + "/" + urllib.quote(identifier)
        if type == "atom":
            return root + ".atom"
        elif type == "ore":
            return root + ".rdf"
            
    def file_uri(self, silo, identifier, filename):
        """ The URL for accessing the parts of an object in the store """
        return self.config.db_base_url + urllib.quote(silo) + "/datasets/" + urllib.quote(identifier) + "/" + urllib.quote(filename)
    
    def interpret_path(self, path):
        accept_parameters = None
        silo = None
        dataset = None
        
        # first figure out the accept parameters from the path suffix and chomp
        # the path down to size
        if path.endswith("rdf"):
            accept_parameters = AcceptParameters(ContentType("application/rdf+xml"))
            path = path[:-4]
        elif path.endswith("atom"):
            accept_parameters = AcceptParameters(ContentType("application/atom+xml;type=feed"))
            path = path[:-5]
        
        # check to see if this has a / separator
        if "/" in path:
            # deconstruct the path into silo/dataset (if possible)
            silo, dataset_id = path.split("/", 1)
        else:
            silo = path
            
        return silo, dataset_id, accept_parameters
        
class DataBankErrors(object):
    dataset_conflict = "http://databank.ox.ac.uk/errors/DatasetConflict"
    
class DataBankStates(object):
    initial_state = ("http://databank.ox.ac.uk/state/EmptyContainer", "Only the container for the dataset has been created so far")
    zip_file_added = ("http://databank.ox.ac.uk/state/ZipFileAdded", "The dataset contains only the zip file")
    content_states = [u"http://databank.ox.ac.uk/state/EmptyContainer", u"http://databank.ox.ac.uk/state/ZipFileAdded"]
    metadata_states = []
